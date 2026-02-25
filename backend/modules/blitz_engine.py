"""
Leomail v4 — Blitz Pipeline Engine
Continuous Birth → Send → Die → Repeat conveyor.
Two async pools: birth_pool feeds send_pool via asyncio.Queue.
"""
import asyncio
import random
import string
from datetime import datetime
from loguru import logger

from ..database import SessionLocal
from ..models import (
    Campaign, CampaignStatus, CampaignTemplate, CampaignLink, CampaignRecipient,
    Account, AccountStatus, Proxy, ProxyStatus, ThreadLog,
)
from ..services.smtp_sender import send_email, SendResult


# ─── Global campaign registry ────────────────────────────────────────────────
# campaign_id → BlitzCampaignRunner instance
_active_campaigns: dict[int, "BlitzCampaignRunner"] = {}


def get_active_campaign(campaign_id: int) -> "BlitzCampaignRunner | None":
    return _active_campaigns.get(campaign_id)


def list_active_campaigns() -> list[int]:
    return list(_active_campaigns.keys())


# ─── Constants ────────────────────────────────────────────────────────────────

SEND_DELAY_MIN = 5       # seconds between emails (per thread)
SEND_DELAY_MAX = 15
MAX_EMAILS_PER_ACCOUNT = 50   # then burn account
MAX_CONSECUTIVE_ERRORS = 3    # kill account after N errors in a row
BIRTH_RETRY_DELAY = 30        # seconds between birth retries on failure
RESOURCE_CHECK_INTERVAL = 300  # check resources every 5 min


class BlitzCampaignRunner:
    """
    Runs a single campaign with two pools:
    - birth_pool: N threads birthing accounts → pushing to send_queue
    - send_pool:  M threads pulling accounts from queue → sending → burning
    """

    def __init__(self, campaign_id: int):
        self.campaign_id = campaign_id
        self.send_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=50)
        self._stop_event = asyncio.Event()
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # not paused initially
        self._birth_tasks: list[asyncio.Task] = []
        self._send_tasks: list[asyncio.Task] = []
        self._monitor_task: asyncio.Task | None = None

    @property
    def is_running(self) -> bool:
        return not self._stop_event.is_set()

    async def start(self):
        """Start the blitz pipeline."""
        db = SessionLocal()
        try:
            campaign = db.query(Campaign).filter(Campaign.id == self.campaign_id).first()
            if not campaign:
                logger.error(f"Blitz: Campaign {self.campaign_id} not found")
                return

            birth_threads = campaign.birth_threads or 10
            send_threads = campaign.send_threads or 20

            logger.info(
                f"Blitz START: campaign={campaign.name} "
                f"birth={birth_threads} send={send_threads}"
            )

            # Start birth pool
            for i in range(birth_threads):
                task = asyncio.create_task(
                    self._birth_worker(i),
                    name=f"blitz-birth-{self.campaign_id}-{i}"
                )
                self._birth_tasks.append(task)

            # Start send pool
            for i in range(send_threads):
                task = asyncio.create_task(
                    self._send_worker(i),
                    name=f"blitz-send-{self.campaign_id}-{i}"
                )
                self._send_tasks.append(task)

            # Start resource monitor
            self._monitor_task = asyncio.create_task(
                self._resource_monitor(),
                name=f"blitz-monitor-{self.campaign_id}"
            )

            _active_campaigns[self.campaign_id] = self

        finally:
            db.close()

    async def stop(self, reason: str = "Manual stop"):
        """Stop the blitz pipeline."""
        self._stop_event.set()
        self._pause_event.set()  # unblock any paused workers

        # Cancel all tasks
        for t in self._birth_tasks + self._send_tasks:
            t.cancel()
        if self._monitor_task:
            self._monitor_task.cancel()

        # Update campaign status
        db = SessionLocal()
        try:
            campaign = db.query(Campaign).filter(Campaign.id == self.campaign_id).first()
            if campaign:
                campaign.status = CampaignStatus.STOPPED
                campaign.stop_reason = reason
                db.commit()
        finally:
            db.close()

        _active_campaigns.pop(self.campaign_id, None)
        logger.info(f"Blitz STOP: campaign={self.campaign_id}, reason={reason}")

    async def pause(self):
        """Pause the pipeline (workers wait)."""
        self._pause_event.clear()
        db = SessionLocal()
        try:
            campaign = db.query(Campaign).filter(Campaign.id == self.campaign_id).first()
            if campaign:
                campaign.status = CampaignStatus.PAUSED
                db.commit()
        finally:
            db.close()
        logger.info(f"Blitz PAUSED: campaign={self.campaign_id}")

    async def resume(self):
        """Resume paused pipeline."""
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
        logger.info(f"Blitz RESUMED: campaign={self.campaign_id}")

    # ─── Birth Worker ─────────────────────────────────────────────────────────

    async def _birth_worker(self, worker_id: int):
        """Birth accounts and push to send queue."""
        while not self._stop_event.is_set():
            await self._pause_event.wait()  # block if paused
            if self._stop_event.is_set():
                break

            db = SessionLocal()
            try:
                campaign = db.query(Campaign).filter(Campaign.id == self.campaign_id).first()
                if not campaign or campaign.status not in (
                    CampaignStatus.RUNNING, CampaignStatus.PAUSED
                ):
                    break

                # Pick provider
                providers = campaign.providers or ["yahoo"]
                provider = random.choice(providers)

                # Get proxy
                proxy = db.query(Proxy).filter(
                    Proxy.status == ProxyStatus.ACTIVE,
                ).first()
                # TODO: Filter by GEO and per-provider usage limits

                if not proxy:
                    logger.warning(f"Blitz birth[{worker_id}]: No proxies available")
                    await asyncio.sleep(BIRTH_RETRY_DELAY)
                    continue

                # Pick name from name pack
                name_pack = campaign.name_pack or "us_names_5k"

                logger.debug(f"Blitz birth[{worker_id}]: birthing {provider} account...")

                # Run birth (in thread to avoid blocking)
                account_data = await self._do_birth(
                    provider, name_pack, proxy, campaign.geo, db
                )

                if account_data:
                    # Push to send queue (blocks if queue is full — backpressure)
                    await self.send_queue.put(account_data)

                    # Update stats
                    campaign = db.query(Campaign).filter(Campaign.id == self.campaign_id).first()
                    if campaign:
                        campaign.accounts_born = (campaign.accounts_born or 0) + 1
                        db.commit()

                    logger.info(
                        f"Blitz birth[{worker_id}]: ✓ {account_data['email']} "
                        f"→ send queue ({self.send_queue.qsize()} waiting)"
                    )
                else:
                    logger.warning(f"Blitz birth[{worker_id}]: birth failed, retrying...")
                    await asyncio.sleep(BIRTH_RETRY_DELAY)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Blitz birth[{worker_id}] error: {e}")
                await asyncio.sleep(BIRTH_RETRY_DELAY)
            finally:
                db.close()

    async def _do_birth(self, provider: str, name_pack: str, proxy, geo: str, db) -> dict | None:
        """
        Execute a single account birth.
        Returns {email, password, first_name, provider, proxy_id} or None.
        
        TODO: Integrate with existing birth modules (gmail.py, yahoo.py, etc.)
        For now, this is a placeholder that will be connected to the real birth pipeline.
        """
        # Import real birth functions
        try:
            from ..modules.birth import (
                register_single_gmail, register_single_yahoo,
                register_single_aol, register_single_outlook,
            )
            from ..modules.browser_manager import BrowserManager
            from ..modules.birth._helpers import get_sms_provider, get_captcha_provider
            from ..config import load_config
            import os

            config = load_config()

            # Load name pack
            name_file = f"backend/data/names/{name_pack}.txt"
            if not os.path.exists(name_file):
                name_file = f"data/names/{name_pack}.txt"
            
            first_name = "Maria"
            last_name = "Silva"
            if os.path.exists(name_file):
                with open(name_file, "r", encoding="utf-8") as f:
                    lines = [l.strip() for l in f if l.strip()]
                if lines:
                    parts = random.choice(lines).split(",")
                    first_name = parts[0] if parts else "Maria"
                    last_name = parts[1] if len(parts) > 1 else "Silva"

            # Select birth function
            birth_funcs = {
                "gmail": register_single_gmail,
                "yahoo": register_single_yahoo,
                "aol": register_single_aol,
                "outlook": register_single_outlook,
                "hotmail": register_single_outlook,
            }
            birth_fn = birth_funcs.get(provider)
            if not birth_fn:
                logger.error(f"Unknown provider for birth: {provider}")
                return None

            # Start browser for birth
            bm = BrowserManager(headless=True)
            await bm.start()
            try:
                result = await birth_fn(
                    browser_manager=bm,
                    proxy=proxy,
                    first_name=first_name,
                    last_name=last_name,
                    geo=geo or "US",
                    gender="female",
                    db=db,
                )

                if result and result.get("success"):
                    return {
                        "email": result["email"],
                        "password": result["password"],
                        "first_name": first_name,
                        "provider": provider,
                        "proxy_id": proxy.id if proxy else None,
                        "account_id": result.get("account_id"),
                    }
                return None
            finally:
                await bm.stop()

        except Exception as e:
            logger.error(f"Birth execution error: {e}")
            return None

    # ─── Send Worker ──────────────────────────────────────────────────────────

    async def _send_worker(self, worker_id: int):
        """Pull accounts from queue, send emails until account dies."""
        while not self._stop_event.is_set():
            await self._pause_event.wait()
            if self._stop_event.is_set():
                break

            # Get account from birth queue
            try:
                account_data = await asyncio.wait_for(
                    self.send_queue.get(), timeout=30
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            db = SessionLocal()
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

                logger.info(f"Blitz send[{worker_id}]: starting with {email}")

                consecutive_errors = 0
                emails_sent = 0

                while (
                    not self._stop_event.is_set()
                    and consecutive_errors < MAX_CONSECUTIVE_ERRORS
                    and emails_sent < MAX_EMAILS_PER_ACCOUNT
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
                        # No more recipients → campaign complete
                        logger.info(f"Blitz send[{worker_id}]: no more recipients")
                        await self.stop("All recipients sent")
                        break

                    # Get template
                    templates = db.query(CampaignTemplate).filter(
                        CampaignTemplate.campaign_id == self.campaign_id,
                        CampaignTemplate.active == True  # noqa
                    ).all()
                    if not templates:
                        await self.stop("No active templates")
                        break

                    template = random.choice(templates)

                    # Get ESP link
                    link = db.query(CampaignLink).filter(
                        CampaignLink.campaign_id == self.campaign_id,
                        CampaignLink.active == True,  # noqa
                        CampaignLink.use_count < CampaignLink.max_uses
                    ).order_by(CampaignLink.use_count.asc()).first()

                    if not link:
                        await self.stop("All ESP links exhausted")
                        break

                    # Randomize link
                    rand_hash = ''.join(random.choices(
                        string.ascii_letters + string.digits, k=6
                    ))
                    link_url = f"{link.esp_url}#{rand_hash}"
                    link.use_count += 1
                    if link.use_count >= link.max_uses:
                        link.active = False

                    # Render template
                    subject = template.subject
                    body = template.body_html
                    subject = subject.replace("{first_name}", from_name)
                    subject = subject.replace("{date}", datetime.utcnow().strftime("%d/%m/%Y"))
                    body = body.replace("{first_name}", from_name)
                    body = body.replace("{date}", datetime.utcnow().strftime("%d/%m/%Y"))

                    # Insert link based on mode
                    if campaign.link_mode == "hyperlink":
                        body = body.replace("{link}", link_url)
                    else:
                        body = body.replace("{link}", link_url)

                    # Mark recipient as sent BEFORE sending (prevent double-send)
                    recipient.sent = True
                    recipient.sent_at = datetime.utcnow()
                    db.commit()

                    # Send via SMTP (blocking call in thread)
                    result, detail = await asyncio.to_thread(
                        send_email,
                        account_email=email,
                        account_password=password,
                        provider=provider,
                        to_email=recipient.email,
                        subject=subject,
                        body_html=body,
                        from_name=from_name,
                    )

                    # Process result
                    if result == SendResult.OK:
                        recipient.result = "ok"
                        emails_sent += 1
                        consecutive_errors = 0
                        template.use_count += 1

                        # Update campaign stats
                        campaign = db.query(Campaign).filter(
                            Campaign.id == self.campaign_id
                        ).first()
                        if campaign:
                            campaign.total_sent = (campaign.total_sent or 0) + 1

                        db.commit()
                        logger.debug(
                            f"Blitz send[{worker_id}] {email} → {recipient.email} ✓ "
                            f"({emails_sent}/{MAX_EMAILS_PER_ACCOUNT})"
                        )

                    elif result == SendResult.RATE_LIMIT:
                        # Temporary — undo sent mark, wait, retry
                        recipient.sent = False
                        recipient.sent_at = None
                        recipient.result = None
                        db.commit()
                        delay = random.uniform(30, 60)
                        logger.info(f"Blitz send[{worker_id}] rate limited, waiting {delay:.0f}s")
                        await asyncio.sleep(delay)
                        consecutive_errors += 1

                    elif result in (SendResult.AUTH_FAIL, SendResult.SUSPENDED):
                        # Account is dead
                        recipient.sent = False
                        recipient.sent_at = None
                        recipient.result = None
                        db.commit()
                        logger.warning(
                            f"Blitz send[{worker_id}] {email} DEAD: {result} — {detail[:80]}"
                        )
                        break  # exit inner loop, get new account

                    elif result == SendResult.BOUNCE:
                        recipient.result = "bounce"
                        campaign = db.query(Campaign).filter(
                            Campaign.id == self.campaign_id
                        ).first()
                        if campaign:
                            campaign.total_errors = (campaign.total_errors or 0) + 1
                        db.commit()
                        consecutive_errors = 0  # bounce is recipient issue, not account

                    elif result == SendResult.NETWORK:
                        recipient.sent = False
                        recipient.sent_at = None
                        recipient.result = None
                        db.commit()
                        consecutive_errors += 1
                        await asyncio.sleep(10)

                    else:
                        recipient.result = "error"
                        campaign = db.query(Campaign).filter(
                            Campaign.id == self.campaign_id
                        ).first()
                        if campaign:
                            campaign.total_errors = (campaign.total_errors or 0) + 1
                        db.commit()
                        consecutive_errors += 1

                    # Delay between emails
                    delay = random.uniform(SEND_DELAY_MIN, SEND_DELAY_MAX)
                    await asyncio.sleep(delay)

                # Account exhausted or dead
                campaign = db.query(Campaign).filter(Campaign.id == self.campaign_id).first()
                if campaign:
                    campaign.accounts_dead = (campaign.accounts_dead or 0) + 1
                    db.commit()

                # Mark account as dead in DB
                if account_data.get("account_id"):
                    acc = db.query(Account).filter(
                        Account.id == account_data["account_id"]
                    ).first()
                    if acc:
                        acc.status = AccountStatus.DEAD
                        db.commit()

                logger.info(
                    f"Blitz send[{worker_id}] {email} burned: "
                    f"sent={emails_sent}, errors={consecutive_errors}"
                )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Blitz send[{worker_id}] error: {e}")
                await asyncio.sleep(5)
            finally:
                db.close()

    # ─── Resource Monitor ─────────────────────────────────────────────────────

    async def _resource_monitor(self):
        """Periodic resource check — auto-pause on critical deficit."""
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

                    # Check remaining recipients
                    remaining = db.query(CampaignRecipient).filter(
                        CampaignRecipient.campaign_id == self.campaign_id,
                        CampaignRecipient.sent == False  # noqa
                    ).count()
                    if remaining == 0:
                        await self.stop("All recipients sent — campaign complete")
                        break

                    # Check remaining links
                    active_links = db.query(CampaignLink).filter(
                        CampaignLink.campaign_id == self.campaign_id,
                        CampaignLink.active == True  # noqa
                    ).count()
                    if active_links == 0:
                        await self.stop("All ESP links exhausted")
                        break

                    # Check active templates
                    active_templates = db.query(CampaignTemplate).filter(
                        CampaignTemplate.campaign_id == self.campaign_id,
                        CampaignTemplate.active == True  # noqa
                    ).count()
                    if active_templates == 0:
                        await self.stop("No active templates")
                        break

                    # Check alive proxies
                    alive_proxies = db.query(Proxy).filter(
                        Proxy.status == ProxyStatus.ACTIVE
                    ).count()
                    if alive_proxies == 0:
                        await self.stop("No alive proxies")
                        break

                    # Log status
                    logger.info(
                        f"Blitz monitor [{campaign.name}]: "
                        f"sent={campaign.total_sent}, queue={self.send_queue.qsize()}, "
                        f"links={active_links}, recipients={remaining}"
                    )

                finally:
                    db.close()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Blitz monitor error: {e}")


# ─── Public API (called from campaigns router) ───────────────────────────────

async def start_blitz(campaign_id: int):
    """Start a blitz campaign."""
    if campaign_id in _active_campaigns:
        raise ValueError(f"Campaign {campaign_id} already running")

    runner = BlitzCampaignRunner(campaign_id)
    await runner.start()
    return runner


async def stop_blitz(campaign_id: int, reason: str = "Manual stop"):
    """Stop a running blitz campaign."""
    runner = _active_campaigns.get(campaign_id)
    if runner:
        await runner.stop(reason)


async def pause_blitz(campaign_id: int):
    """Pause a running blitz campaign."""
    runner = _active_campaigns.get(campaign_id)
    if runner:
        await runner.pause()


async def resume_blitz(campaign_id: int):
    """Resume a paused blitz campaign."""
    runner = _active_campaigns.get(campaign_id)
    if runner:
        await runner.resume()
