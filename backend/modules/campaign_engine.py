"""
Leomail v4 - Campaign Engine (Send-Only)
Loads Ready accounts from farms -> sends emails via browser -> tracks results.
No account creation — autoreg is a separate module.
"""
import asyncio
import random
import string
import time
from datetime import datetime
from loguru import logger

from ..database import SessionLocal
from ..models import (
    Campaign, CampaignStatus, CampaignTemplate, CampaignLink, CampaignRecipient,
    Account, AccountStatus, Proxy, ProxyStatus,
)


# ─── Global campaign registry ────────────────────────────────────────────────
_active_campaigns: dict[int, "CampaignRunner"] = {}


def get_active_campaign(campaign_id: int) -> "CampaignRunner | None":
    return _active_campaigns.get(campaign_id)


def list_active_campaigns() -> list[int]:
    return list(_active_campaigns.keys())


# ─── Constants ────────────────────────────────────────────────────────────────

MAX_CONSECUTIVE_ERRORS = 3    # kill account after N errors in a row
SEND_RETRY_DELAY = 30         # seconds between retries on failure
RESOURCE_CHECK_INTERVAL = 300  # check resources every 5 min
RESOURCE_WAIT_TIMEOUT = 300   # wait up to 5 min for user to add links/templates
ACCOUNT_COOLDOWN_SECONDS = 3600  # 1 hour cooldown after hitting daily limit

# ── Provider-specific daily sending limits ──
PROVIDER_DAILY_LIMITS = {
    "yahoo": 20, "aol": 20,
    "outlook": 30, "hotmail": 30,
    "gmail": 25, "proton": 15,
    "webde": 20,
}
DEFAULT_DAILY_LIMIT = 25

# ── Progressive warmup delay schedule (seconds) ──
# After each email, wait this long before the next one.
# Ramps down from 10 min to 1 min, then stays at 1 min.
WARMUP_DELAYS = [
    600,   # after 1st email: 10 min
    600,   # after 2nd: 10 min
    600,   # after 3rd: 10 min
    300,   # after 4th: 5 min
    240,   # after 5th: 4 min
    180,   # after 6th: 3 min
    120,   # after 7th: 2 min
    60,    # after 8th+: 1 min (minimum)
]


def get_warmup_delay(emails_sent: int) -> float:
    """Get delay in seconds based on how many emails this account has sent."""
    if emails_sent < len(WARMUP_DELAYS):
        base = WARMUP_DELAYS[emails_sent]
    else:
        base = WARMUP_DELAYS[-1]  # 60 seconds minimum
    jitter = random.uniform(0.85, 1.15)
    return base * jitter


class CampaignRunner:
    """
    Runs a send-only campaign:
    - Loads Ready accounts from linked farms
    - Opens browser sessions for each account
    - Sends emails via browser UI (Yahoo/AOL/Gmail/Outlook/Proton)
    - Tracks send stats, rate limits, dead accounts
    """

    def __init__(self, campaign_id: int):
        self.campaign_id = campaign_id
        self.account_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=200)
        self._stop_event = asyncio.Event()
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # not paused initially
        self._send_tasks: list[asyncio.Task] = []
        self._monitor_task: asyncio.Task | None = None
        self._template_idx = 0  # round-robin template counter
        self._accounts_rotated = 0  # accounts re-queued after daily limit

    @property
    def is_running(self) -> bool:
        return not self._stop_event.is_set()

    async def start(self):
        """Start the campaign — load accounts from farms, launch send workers."""
        db = SessionLocal()
        try:
            campaign = db.query(Campaign).filter(Campaign.id == self.campaign_id).first()
            if not campaign:
                logger.error(f"Campaign {self.campaign_id} not found")
                return

            send_threads = campaign.send_threads or 10

            # ── Load accounts from farms into send queue ──
            loaded = 0
            farm_ids = campaign.farm_ids if isinstance(campaign.farm_ids, list) else []
            if farm_ids:
                from ..models import Farm, farm_accounts
                accs = (
                    db.query(Account)
                    .join(farm_accounts)
                    .filter(
                        farm_accounts.c.farm_id.in_(farm_ids),
                        Account.status.notin_(["dead", "banned"]),
                    )
                    .all()
                )
                for acc in accs:
                    await self.account_queue.put({
                        "email": acc.email,
                        "password": acc.password,
                        "provider": acc.provider,
                        "first_name": acc.first_name or "",
                        "account_id": acc.id,
                        "prior_sends": acc.total_emails_sent or 0,
                    })
                    loaded += 1

            if loaded == 0:
                logger.error(f"Campaign {campaign.name}: no accounts found in farms {farm_ids}")
                campaign.status = CampaignStatus.STOPPED
                campaign.stop_reason = "No accounts in selected farms"
                db.commit()
                return

            logger.info(
                f"Campaign START: {campaign.name} — "
                f"{loaded} accounts loaded, {send_threads} send threads"
            )

            # Start send workers
            for i in range(send_threads):
                task = asyncio.create_task(
                    self._send_worker(i),
                    name=f"campaign-send-{self.campaign_id}-{i}"
                )
                self._send_tasks.append(task)

            # Start resource monitor
            self._monitor_task = asyncio.create_task(
                self._resource_monitor(),
                name=f"campaign-monitor-{self.campaign_id}"
            )

            _active_campaigns[self.campaign_id] = self

        finally:
            db.close()

    async def stop(self, reason: str = "Manual stop"):
        """Stop the campaign and generate task report."""
        self._stop_event.set()
        self._pause_event.set()  # unblock any paused workers

        for t in self._send_tasks:
            t.cancel()
        if self._monitor_task:
            self._monitor_task.cancel()

        db = SessionLocal()
        try:
            campaign = db.query(Campaign).filter(Campaign.id == self.campaign_id).first()
            if campaign:
                campaign.status = CampaignStatus.STOPPED
                campaign.stop_reason = reason
                db.commit()
        finally:
            db.close()

        # ── Generate task report on completion ──
        try:
            from ..services.task_report import task_report
            report = task_report.generate(self.campaign_id)
            if report and "error" not in report:
                logger.info(
                    f"Campaign REPORT: id={self.campaign_id} | "
                    f"sent={report.get('accounts', {}).get('created', 0)}, "
                    f"cost=${report.get('grand_total', 0)}, "
                    f"rotated={self._accounts_rotated}"
                )
        except Exception as e:
            logger.debug(f"Campaign report generation failed: {e}")

        _active_campaigns.pop(self.campaign_id, None)
        logger.info(f"Campaign STOP: id={self.campaign_id}, reason={reason}")

    async def pause(self):
        """Pause the campaign (workers wait)."""
        self._pause_event.clear()
        db = SessionLocal()
        try:
            campaign = db.query(Campaign).filter(Campaign.id == self.campaign_id).first()
            if campaign:
                campaign.status = CampaignStatus.PAUSED
                db.commit()
        finally:
            db.close()
        logger.info(f"Campaign PAUSED: id={self.campaign_id}")

    async def resume(self):
        """Resume paused campaign."""
        self._pause_event.set()
        db = SessionLocal()
        try:
            campaign = db.query(Campaign).filter(Campaign.id == self.campaign_id).first()
            if campaign:
                campaign.status = CampaignStatus.RUNNING
                campaign.stop_reason = None
                db.commit()
        finally:
            db.close()
        logger.info(f"Campaign RESUMED: id={self.campaign_id}")

    # ─── Send Worker ──────────────────────────────────────────────────────────

    async def _send_worker(self, worker_id: int):
        """Pull accounts from queue, send emails via BROWSER.
        Smart rotation: re-queues accounts after daily limit.
        Template cycling: round-robin instead of deactivation.
        ErrorHandler: consistent error classification.
        """
        from ..browser_manager import BrowserManager
        from ..services.error_handler import ErrorHandler

        while not self._stop_event.is_set():
            await self._pause_event.wait()
            if self._stop_event.is_set():
                break

            # Get account from queue
            try:
                account_data = await asyncio.wait_for(
                    self.account_queue.get(), timeout=30
                )
            except asyncio.TimeoutError:
                # No more accounts in queue — worker exits
                logger.info(f"Campaign send[{worker_id}]: no more accounts in queue")
                break
            except asyncio.CancelledError:
                break

            # ── Check cooldown (smart rotation) ──
            cooldown_until = account_data.get("cooldown_until", 0)
            if cooldown_until > time.time():
                # Not ready yet — re-queue for later
                try:
                    self.account_queue.put_nowait(account_data)
                except asyncio.QueueFull:
                    pass
                await asyncio.sleep(5)
                continue

            db = SessionLocal()
            bm = None
            page = None
            context = None
            account_dead = False
            try:
                campaign = db.query(Campaign).filter(Campaign.id == self.campaign_id).first()
                if not campaign or campaign.status not in (
                    CampaignStatus.RUNNING, CampaignStatus.PAUSED
                ):
                    break

                email = account_data["email"]
                password = account_data["password"]
                provider = account_data["provider"]
                from_name = account_data.get("first_name", "")
                account_id = account_data.get("account_id")
                daily_limit = PROVIDER_DAILY_LIMITS.get(provider, DEFAULT_DAILY_LIMIT)

                # ── ErrorHandler for this account ──
                error_handler = ErrorHandler(
                    account_email=email,
                    engine="campaign",
                )

                logger.info(f"Campaign send[{worker_id}]: starting with {email} (limit: {daily_limit}/day)")

                consecutive_errors = 0
                emails_sent = 0
                warmup_level = account_data.get("prior_sends", 0)

                # ── Open browser for this account ──
                bm = BrowserManager(headless=True)
                await bm.start()

                # Load saved session if available
                if account_id:
                    acc_obj = db.query(Account).filter(Account.id == account_id).first()
                    if acc_obj and hasattr(bm, 'load_session_context'):
                        try:
                            context, _ = await bm.load_session_context(
                                account_id=account_id,
                                proxy=acc_obj.proxy,
                                geo=acc_obj.geo,
                            )
                        except Exception as e:
                            logger.warning(f"Campaign send[{worker_id}]: session load failed: {e}")
                            context = None

                if not context:
                    context = await bm.new_context(proxy=None)

                page = await context.new_page()

                # ── Navigate to webmail ──
                MAIL_URLS = {
                    "yahoo": "https://mail.yahoo.com/",
                    "aol": "https://mail.aol.com/",
                    "gmail": "https://mail.google.com",
                    "outlook": "https://outlook.live.com/mail",
                    "hotmail": "https://outlook.live.com/mail",
                    "proton": "https://mail.proton.me",
                    "webde": "https://web.de/email/",
                }
                mail_url = MAIL_URLS.get(provider, "https://mail.yahoo.com/")
                try:
                    await page.goto(mail_url, wait_until="domcontentloaded", timeout=30000)
                    await asyncio.sleep(random.uniform(3, 6))
                except Exception as e:
                    logger.error(f"Campaign send[{worker_id}]: failed to open {mail_url}: {e}")
                    continue

                # Check if session is valid (not redirected to login)
                if "signin" in page.url or "login" in page.url or "account" in page.url:
                    logger.info(f"Campaign send[{worker_id}] {email}: session expired, attempting re-login...")
                    from .browser_relogin import browser_relogin
                    relogin_ok = await browser_relogin(page, provider, email, password)
                    if relogin_ok:
                        # Save new session for future use
                        try:
                            if account_id and hasattr(bm, 'save_session'):
                                await bm.save_session(context, account_id)
                            logger.info(f"Campaign send[{worker_id}] {email}: re-login successful, session saved")
                        except Exception as se:
                            logger.warning(f"Campaign send[{worker_id}] {email}: session save after re-login failed: {se}")
                    else:
                        logger.warning(f"Campaign send[{worker_id}] {email}: re-login failed, marking dead")
                        account_dead = True
                        if account_id:
                            acc = db.query(Account).filter(Account.id == account_id).first()
                            if acc:
                                acc.status = AccountStatus.DEAD
                                db.commit()
                        continue

                # ── Send loop (reuses same browser page) ──
                while (
                    not self._stop_event.is_set()
                    and consecutive_errors < MAX_CONSECUTIVE_ERRORS
                    and emails_sent < daily_limit
                ):
                    await self._pause_event.wait()
                    if self._stop_event.is_set():
                        break

                    # Get next recipient
                    recipient = db.query(CampaignRecipient).filter(
                        CampaignRecipient.campaign_id == self.campaign_id,
                        CampaignRecipient.sent == False  # noqa
                    ).first()

                    if not recipient:
                        logger.info(f"Campaign send[{worker_id}]: no more recipients")
                        await self.stop("All recipients sent")
                        break

                    # ── Template rotation (round-robin) ──
                    templates = db.query(CampaignTemplate).filter(
                        CampaignTemplate.campaign_id == self.campaign_id,
                        CampaignTemplate.active == True  # noqa
                    ).all()

                    if not templates:
                        logger.warning(f"Campaign send[{worker_id}]: no active templates, waiting...")
                        for _ in range(RESOURCE_WAIT_TIMEOUT // 10):
                            await asyncio.sleep(10)
                            if self._stop_event.is_set():
                                break
                            templates = db.query(CampaignTemplate).filter(
                                CampaignTemplate.campaign_id == self.campaign_id,
                                CampaignTemplate.active == True
                            ).all()
                            if templates:
                                break
                        if not templates:
                            await self.stop("No active templates (waited 5 min)")
                            break

                    # Round-robin: cycle through templates without deactivating
                    template = templates[self._template_idx % len(templates)]
                    self._template_idx += 1
                    template_id = template.id
                    template.use_count = (template.use_count or 0) + 1
                    db.commit()

                    # Get ESP link
                    link = db.query(CampaignLink).filter(
                        CampaignLink.campaign_id == self.campaign_id,
                        CampaignLink.active == True,  # noqa
                        CampaignLink.use_count < CampaignLink.max_uses
                    ).order_by(CampaignLink.use_count.asc()).first()

                    if not link:
                        logger.warning(f"Campaign send[{worker_id}]: all links exhausted, waiting...")
                        for _ in range(RESOURCE_WAIT_TIMEOUT // 10):
                            await asyncio.sleep(10)
                            if self._stop_event.is_set():
                                break
                            link = db.query(CampaignLink).filter(
                                CampaignLink.campaign_id == self.campaign_id,
                                CampaignLink.active == True,
                                CampaignLink.use_count < CampaignLink.max_uses
                            ).order_by(CampaignLink.use_count.asc()).first()
                            if link:
                                break
                        if not link:
                            await self.stop("All links exhausted (waited 5 min)")
                            break

                    # Randomize link
                    rand_hash = ''.join(random.choices(
                        string.ascii_letters + string.digits, k=6
                    ))
                    link_url = f"{link.esp_url}#{rand_hash}"
                    link_id = link.id

                    # Render template with variables
                    subject = template.subject
                    body = template.body_html

                    to_email_str = recipient.email or ""
                    username = to_email_str.split("@")[0] if "@" in to_email_str else to_email_str
                    subject = subject.replace("{{USERNAME}}", username)
                    body = body.replace("{{USERNAME}}", username)

                    to_name = getattr(recipient, 'first_name', '') or ''
                    if not to_name:
                        to_name = username
                    subject = subject.replace("{{NAME}}", to_name)
                    body = body.replace("{{NAME}}", to_name)
                    subject = subject.replace("{{FIRSTNAME}}", to_name)
                    body = body.replace("{{FIRSTNAME}}", to_name)
                    subject = subject.replace("{first_name}", from_name)
                    body = body.replace("{first_name}", from_name)

                    date_str = datetime.utcnow().strftime("%d/%m/%Y")
                    subject = subject.replace("{{DATE}}", date_str).replace("{date}", date_str)
                    body = body.replace("{{DATE}}", date_str).replace("{date}", date_str)

                    body = body.replace("{{LINK}}", link_url)
                    subject = subject.replace("{{LINK}}", link_url)
                    body = body.replace("{link}", link_url)

                    # Lock recipient
                    recipient.sent = True
                    recipient.sent_at = datetime.utcnow()
                    db.commit()

                    # ═══ BROWSER COMPOSE & SEND ═══
                    send_ok = False
                    send_error = ""

                    try:
                        await self._browser_compose_send(
                            page, provider, recipient.email, subject, body
                        )
                        send_ok = True
                    except Exception as e:
                        send_error = str(e)
                        logger.warning(
                            f"Campaign send[{worker_id}] {email} -> {recipient.email} "
                            f"ERROR: {send_error[:200]}"
                        )

                    # ═══ Process result via ErrorHandler ═══
                    if send_ok:
                        recipient.result = "ok"
                        emails_sent += 1
                        warmup_level += 1
                        consecutive_errors = 0
                        error_handler.record_sent()

                        link = db.query(CampaignLink).filter(
                            CampaignLink.id == link_id
                        ).first()
                        if link:
                            link.use_count += 1
                            if link.use_count >= link.max_uses:
                                link.active = False

                        campaign = db.query(Campaign).filter(
                            Campaign.id == self.campaign_id
                        ).first()
                        if campaign:
                            campaign.total_sent = (campaign.total_sent or 0) + 1

                        if account_id:
                            acc = db.query(Account).filter(
                                Account.id == account_id
                            ).first()
                            if acc:
                                acc.total_emails_sent = (acc.total_emails_sent or 0) + 1
                                acc.emails_sent_today = (acc.emails_sent_today or 0) + 1

                        db.commit()
                        logger.debug(
                            f"Campaign send[{worker_id}] {email} -> {recipient.email} "
                            f"({emails_sent}/{daily_limit})"
                        )

                    else:
                        # ── Use ErrorHandler for classification ──
                        action = error_handler.handle_error(send_error)

                        if action == "mark_dead":
                            # Undo recipient, mark account dead
                            recipient.sent = False
                            recipient.sent_at = None
                            recipient.result = None
                            account_dead = True
                            campaign = db.query(Campaign).filter(
                                Campaign.id == self.campaign_id
                            ).first()
                            if campaign:
                                campaign.total_errors = (campaign.total_errors or 0) + 1
                                campaign.accounts_dead = (campaign.accounts_dead or 0) + 1
                            if account_id:
                                acc = db.query(Account).filter(Account.id == account_id).first()
                                if acc:
                                    acc.status = AccountStatus.DEAD
                            db.commit()
                            logger.warning(
                                f"Campaign send[{worker_id}] {email} DEAD: {send_error[:80]}"
                            )
                            break

                        elif action == "pause":
                            # Rate limited — undo recipient, re-queue with cooldown
                            recipient.sent = False
                            recipient.sent_at = None
                            recipient.result = None
                            db.commit()
                            logger.warning(
                                f"Campaign send[{worker_id}] {email} RATE LIMITED -> cooldown"
                            )
                            # Re-queue with cooldown (smart rotation)
                            account_data["cooldown_until"] = time.time() + ACCOUNT_COOLDOWN_SECONDS
                            account_data["prior_sends"] = warmup_level
                            try:
                                self.account_queue.put_nowait(account_data)
                                self._accounts_rotated += 1
                            except asyncio.QueueFull:
                                pass
                            break

                        else:
                            # Retry or unknown — generic error
                            recipient.result = "error"
                            campaign = db.query(Campaign).filter(
                                Campaign.id == self.campaign_id
                            ).first()
                            if campaign:
                                campaign.total_errors = (campaign.total_errors or 0) + 1
                            db.commit()
                            consecutive_errors += 1

                    # Progressive warmup delay
                    delay = get_warmup_delay(warmup_level)
                    if warmup_level <= len(WARMUP_DELAYS):
                        logger.debug(
                            f"Campaign send[{worker_id}] {email}: warmup delay "
                            f"{delay:.0f}s (level={warmup_level}, sent={emails_sent})"
                        )
                    await asyncio.sleep(delay)

                # ── Account finished its batch ──
                if not account_dead and emails_sent >= daily_limit:
                    # Hit daily limit — re-queue with cooldown (smart rotation)
                    account_data["cooldown_until"] = time.time() + ACCOUNT_COOLDOWN_SECONDS
                    account_data["prior_sends"] = warmup_level
                    try:
                        self.account_queue.put_nowait(account_data)
                        self._accounts_rotated += 1
                        logger.info(
                            f"Campaign send[{worker_id}] {email}: daily limit ({daily_limit}) hit "
                            f"-> re-queued with {ACCOUNT_COOLDOWN_SECONDS}s cooldown"
                        )
                    except asyncio.QueueFull:
                        logger.warning(f"Campaign send[{worker_id}] {email}: queue full, cannot re-queue")
                elif account_dead:
                    # Only count actual dead accounts
                    campaign = db.query(Campaign).filter(Campaign.id == self.campaign_id).first()
                    if campaign:
                        # accounts_dead already incremented in error handler above
                        db.commit()

                logger.info(
                    f"Campaign send[{worker_id}] {email} done: "
                    f"sent={emails_sent}, errors={consecutive_errors}, dead={account_dead}"
                )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Campaign send[{worker_id}] error: {e}")
                await asyncio.sleep(5)
            finally:
                if page:
                    try:
                        await page.close()
                    except Exception:
                        pass
                if context:
                    try:
                        await context.close()
                    except Exception:
                        pass
                if bm:
                    try:
                        await bm.stop()
                    except Exception:
                        pass
                db.close()

    # ─── Browser Compose & Send ─────────────────────────────────────────────

    async def _browser_compose_send(
        self, page, provider: str, to_email: str, subject: str, body: str
    ):
        """
        Compose and send one email via browser UI.
        Delegates to shared browser_mail_sender module.
        """
        from .browser_mail_sender import browser_compose_send
        await browser_compose_send(page, provider, to_email, subject, body)

    # ─── Resource Monitor ─────────────────────────────────────────────────────

    async def _resource_monitor(self):
        """Periodic resource check — auto-stop on critical deficit."""
        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(RESOURCE_CHECK_INTERVAL)
                if self._stop_event.is_set():
                    break

                db = SessionLocal()
                try:
                    campaign = db.query(Campaign).filter(
                        Campaign.id == self.campaign_id
                    ).first()
                    if not campaign:
                        break

                    remaining = db.query(CampaignRecipient).filter(
                        CampaignRecipient.campaign_id == self.campaign_id,
                        CampaignRecipient.sent == False  # noqa
                    ).count()
                    if remaining == 0:
                        await self.stop("All recipients sent — campaign complete")
                        break

                    active_links = db.query(CampaignLink).filter(
                        CampaignLink.campaign_id == self.campaign_id,
                        CampaignLink.active == True  # noqa
                    ).count()
                    if active_links == 0:
                        await self.stop("All ESP links exhausted")
                        break

                    active_templates = db.query(CampaignTemplate).filter(
                        CampaignTemplate.campaign_id == self.campaign_id,
                        CampaignTemplate.active == True  # noqa
                    ).count()
                    if active_templates == 0:
                        await self.stop("No active templates")
                        break

                    logger.info(
                        f"Campaign monitor [{campaign.name}]: "
                        f"sent={campaign.total_sent}, "
                        f"links={active_links}, recipients={remaining}"
                    )

                finally:
                    db.close()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Campaign monitor error: {e}")


# ─── Public API (called from campaigns router) ───────────────────────────────

async def start_campaign_engine(campaign_id: int):
    """Start a campaign."""
    if campaign_id in _active_campaigns:
        raise ValueError(f"Campaign {campaign_id} already running")

    runner = CampaignRunner(campaign_id)
    await runner.start()
    return runner


async def stop_campaign_engine(campaign_id: int, reason: str = "Manual stop"):
    """Stop a running campaign."""
    runner = _active_campaigns.get(campaign_id)
    if runner:
        await runner.stop(reason)


async def pause_campaign_engine(campaign_id: int):
    """Pause a running campaign."""
    runner = _active_campaigns.get(campaign_id)
    if runner:
        await runner.pause()


async def resume_campaign_engine(campaign_id: int):
    """Resume a paused campaign."""
    runner = _active_campaigns.get(campaign_id)
    if runner:
        await runner.resume()
