"""
Leomail v4 - Blitz Pipeline Engine
Continuous Birth -> Send -> Die -> Repeat conveyor.
Two async pools: birth_pool feeds send_pool via asyncio.Queue.
"""
import asyncio
import random
import string
import threading
from datetime import datetime
from loguru import logger

from ..database import SessionLocal
from ..models import (
    Campaign, CampaignStatus, CampaignTemplate, CampaignLink, CampaignRecipient,
    Account, AccountStatus, Proxy, ProxyStatus, ThreadLog,
)
from ..services.smtp_sender import send_email, SendResult


# ─── Global campaign registry ────────────────────────────────────────────────
# campaign_id -> BlitzCampaignRunner instance
_active_campaigns: dict[int, "BlitzCampaignRunner"] = {}


def get_active_campaign(campaign_id: int) -> "BlitzCampaignRunner | None":
    return _active_campaigns.get(campaign_id)


def list_active_campaigns() -> list[int]:
    return list(_active_campaigns.keys())


# ─── Constants ────────────────────────────────────────────────────────────────

MAX_EMAILS_PER_ACCOUNT = 50   # then burn account
MAX_CONSECUTIVE_ERRORS = 3    # kill account after N errors in a row
BIRTH_RETRY_DELAY = 30        # seconds between birth retries on failure
RESOURCE_CHECK_INTERVAL = 300  # check resources every 5 min
RESOURCE_WAIT_TIMEOUT = 300   # wait up to 5 min for user to add links/templates

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


# ── Auto GEO -> Name Pack mapping ──
GEO_NAME_PACK_MAP = {
    "AR": "argentina_5k", "BO": "bolivia_5k", "BR": "brazil_5k",
    "CA": "canada_5k", "CL": "chile_5k", "CO": "colombia_5k",
    "CR": "costa_rica_5k", "CU": "cuba_5k", "DO": "dominican_5k",
    "EC": "ecuador_5k", "EG": "egypt_5k", "SV": "el_salvador_5k",
    "GT": "guatemala_5k", "HN": "honduras_5k", "MX": "mexico_5k",
    "NI": "nicaragua_5k", "NG": "nigeria_5k", "PA": "panama_5k",
    "PY": "paraguay_5k", "PE": "peru_5k", "PR": "puerto_rico_5k",
    "ZA": "south_africa_5k", "UY": "uruguay_5k", "US": "us_names_5k",
    "VE": "venezuela_5k",
    "GB": "us_uk", "UK": "us_uk", "AU": "us_uk", "NZ": "us_uk",
    "DE": "europe_de_fr_it", "FR": "europe_de_fr_it", "IT": "europe_de_fr_it",
    "RU": "ru_cis", "UA": "ru_cis", "KZ": "ru_cis", "BY": "ru_cis",
    "SA": "arab", "AE": "arab",
    "KE": "africa", "TZ": "africa",
}

def resolve_name_pack(campaign_name_pack: str, geo: str) -> str:
    """Auto-resolve name pack: explicit > GEO mapping > us_names_5k."""
    if campaign_name_pack and campaign_name_pack != "auto":
        return campaign_name_pack
    geo_upper = (geo or "").upper().strip()
    if geo_upper in GEO_NAME_PACK_MAP:
        return GEO_NAME_PACK_MAP[geo_upper]
    return "us_names_5k"


class BlitzCampaignRunner:
    """
    Runs a single campaign with two pools:
    - birth_pool: N threads birthing accounts -> pushing to send_queue
    - send_pool:  M threads pulling accounts from queue -> sending -> burning
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

            # ── Pre-load existing farm accounts into send queue ──
            existing_count = 0
            if campaign.use_existing and campaign.farm_ids:
                from ..models import Account, Farm, farm_accounts
                farm_id_list = campaign.farm_ids if isinstance(campaign.farm_ids, list) else []
                if farm_id_list:
                    # Get all alive accounts from selected farms
                    accs = (
                        db.query(Account)
                        .join(farm_accounts)
                        .filter(
                            farm_accounts.c.farm_id.in_(farm_id_list),
                            Account.status.notin_(["dead", "banned"]),
                        )
                        .all()
                    )
                    for acc in accs:
                        await self.send_queue.put({
                            "email": acc.email,
                            "password": acc.password,
                            "provider": acc.provider,
                            "first_name": acc.first_name or "",
                            "account_id": acc.id,
                            "is_existing": True,
                            "prior_sends": acc.total_emails_sent or 0,
                        })
                        existing_count += 1
                    logger.info(
                        f"Blitz START: loaded {existing_count} existing accounts "
                        f"from farms {farm_id_list}"
                    )

            logger.info(
                f"Blitz START: campaign={campaign.name} "
                f"birth={birth_threads} send={send_threads} "
                f"existing={existing_count}"
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

                # Pick provider (hotmail = outlook)
                providers = campaign.providers or ["yahoo"]
                raw_provider = random.choice(providers)
                provider = "outlook" if raw_provider == "hotmail" else raw_provider

                # Get proxy - round-robin distribution across workers
                # Each worker offsets into the pool so threads don't all grab the same proxy
                # Apply cooldown filter (same as birth.py)
                from datetime import datetime, timedelta
                cooldown_min = {"yahoo": 30, "aol": 30, "gmail": 30,
                                "outlook": 15, "hotmail": 15}.get(provider.lower(), 20)
                cutoff = datetime.utcnow() - timedelta(minutes=cooldown_min)
                active_proxies = db.query(Proxy).filter(
                    Proxy.status == ProxyStatus.ACTIVE,
                    (Proxy.last_used_at == None) | (Proxy.last_used_at < cutoff),  # noqa: E711
                ).order_by(Proxy.fail_count.asc(), Proxy.id.asc()).all()

                if not active_proxies:
                    logger.warning(f"Blitz birth[{worker_id}]: No proxies available (cooldown {cooldown_min}min)")
                    await asyncio.sleep(BIRTH_RETRY_DELAY)
                    continue

                # Round-robin: each worker picks a different proxy from the pool
                proxy = active_proxies[worker_id % len(active_proxies)]
                proxy.last_used_at = datetime.utcnow()
                db.commit()

                name_pack = resolve_name_pack(campaign.name_pack, campaign.geo)

                logger.debug(f"Blitz birth[{worker_id}]: birthing {provider} via proxy {proxy.id} ({proxy.host}:{proxy.port})...")

                account_data = await self._do_birth(
                    provider, name_pack, proxy, campaign.geo, db
                )

                if account_data:
                    await self.send_queue.put(account_data)

                    # Update stats + reset proxy fail counter on success
                    campaign = db.query(Campaign).filter(Campaign.id == self.campaign_id).first()
                    if campaign:
                        campaign.accounts_born = (campaign.accounts_born or 0) + 1
                    proxy.fail_count = 0  # reset consecutive fails
                    proxy.total_births = (proxy.total_births or 0) + 1  # track lifetime success
                    db.commit()

                    logger.info(
                        f"Blitz birth[{worker_id}]: {account_data['email']} "
                        f"-> send queue ({self.send_queue.qsize()} waiting)"
                    )
                else:
                    # Birth failed - increment proxy fail counter
                    proxy.fail_count = (proxy.fail_count or 0) + 1
                    proxy.total_fails = (proxy.total_fails or 0) + 1  # track lifetime fails

                    # Smart DEAD detection:
                    # 1) 5 consecutive fails = DEAD
                    # 2) OR lifetime success rate < 20% after 10+ attempts = DEAD
                    total_attempts = (proxy.total_births or 0) + (proxy.total_fails or 0)
                    success_rate = (proxy.total_births or 0) / max(total_attempts, 1)

                    if proxy.fail_count >= 5:
                        proxy.status = ProxyStatus.DEAD
                        logger.warning(
                            f"Blitz birth[{worker_id}]: proxy {proxy.id} -> DEAD (5 consecutive fails)"
                        )
                    elif total_attempts >= 10 and success_rate < 0.2:
                        proxy.status = ProxyStatus.DEAD
                        logger.warning(
                            f"Blitz birth[{worker_id}]: proxy {proxy.id} -> DEAD "
                            f"(success rate {success_rate:.0%} after {total_attempts} attempts)"
                        )
                    db.commit()

                    # Adaptive cooldown: more fails = longer wait
                    cooldown = min(BIRTH_RETRY_DELAY * proxy.fail_count, 120)
                    logger.warning(
                        f"Blitz birth[{worker_id}]: birth failed "
                        f"(proxy {proxy.id} fails: {proxy.fail_count}, cooldown: {cooldown}s)"
                    )
                    await asyncio.sleep(cooldown)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Blitz birth[{worker_id}] error: {e}")
                await asyncio.sleep(BIRTH_RETRY_DELAY)
            finally:
                db.close()

    async def _do_birth(self, provider: str, name_pack: str, proxy, geo: str, db) -> dict | None:
        """
        Execute a single account birth using real birth modules.
        Returns {email, password, first_name, provider, proxy_id, account_id} or None.
        """
        from ..birth import (
            register_single_gmail, register_single_yahoo,
            register_single_aol, register_single_outlook,
        )
        from ..browser_manager import BrowserManager
        from ..birth._helpers import get_sms_provider, get_captcha_provider, get_sms_chain
        import os, json

        # ── Load name pack ──
        name_pool = []
        for name_dir in ["user_data/names", "backend/data/names", "data/names"]:
            name_file = os.path.join(name_dir, f"{name_pack}.txt")
            if os.path.exists(name_file):
                with open(name_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        parts = line.split(",")
                        first = parts[0].strip()
                        last = parts[1].strip() if len(parts) > 1 else "Smith"
                        if first:
                            name_pool.append((first, last))
                break

        if not name_pool:
            # Fallback - generate random
            name_pool = [("Maria", "Silva"), ("Jessica", "Smith"), ("Sarah", "Johnson")]
            logger.warning(f"Blitz: name pack '{name_pack}' not found, using fallback names")

        # ── Get SMS provider (with fallback chain) ──
        sms_provider = None
        sms_chain = get_sms_chain("simsms")
        if sms_chain:
            sms_provider = sms_chain[0][1]  # (name, provider_instance)

        # ── Get Captcha provider ──
        captcha_provider = get_captcha_provider()

        # ── Create ThreadLog for this birth ──
        thread_log = ThreadLog(
            task_id=0,
            thread_number=0,
            status="running",
            current_action=f"Blitz birth: {provider}",
        )
        db.add(thread_log)
        db.commit()

        # ── Start browser ──
        bm = BrowserManager(headless=True)
        await bm.start()

        active_pages = {}
        cancel_event = threading.Event()

        try:
            account = None

            if provider == "yahoo":
                account = await register_single_yahoo(
                    browser_manager=bm,
                    proxy=proxy,
                    device_type="desktop",
                    name_pool=name_pool,
                    sms_provider=sms_provider,
                    db=db,
                    thread_log=thread_log,
                    captcha_provider=captcha_provider,
                    ACTIVE_PAGES=active_pages,
                    BIRTH_CANCEL_EVENT=cancel_event,
                )

            elif provider == "aol":
                account = await register_single_aol(
                    browser_manager=bm,
                    proxy=proxy,
                    device_type="desktop",
                    name_pool=name_pool,
                    sms_provider=sms_provider,
                    db=db,
                    thread_log=thread_log,
                    captcha_provider=captcha_provider,
                    ACTIVE_PAGES=active_pages,
                    BIRTH_CANCEL_EVENT=cancel_event,
                )

            elif provider == "outlook":
                domain = "outlook.com"
                account = await register_single_outlook(
                    browser_manager=bm,
                    proxy=proxy,
                    device_type="desktop",
                    name_pool=name_pool,
                    captcha_provider=captcha_provider,
                    db=db,
                    thread_log=thread_log,
                    domain=domain,
                    ACTIVE_PAGES=active_pages,
                    BIRTH_CANCEL_EVENT=cancel_event,
                )

            elif provider == "gmail":
                account = await register_single_gmail(
                    browser_manager=bm,
                    proxy=proxy,
                    name_pool=name_pool,
                    captcha_provider=captcha_provider,
                    sms_provider=sms_provider,
                    db=db,
                    thread_log=thread_log,
                    ACTIVE_PAGES=active_pages,
                    BIRTH_CANCEL_EVENT=cancel_event,
                )

            else:
                logger.error(f"Unknown provider: {provider}")
                return None

            # ── Process result ──
            if account and isinstance(account, Account):
                return {
                    "email": account.email,
                    "password": account.password,
                    "first_name": account.first_name or "",
                    "provider": provider,
                    "proxy_id": proxy.id if proxy else None,
                    "account_id": account.id,
                }
            return None

        except Exception as e:
            logger.error(f"Birth execution error ({provider}): {e}")
            return None
        finally:
            # Close all open pages
            for pid, pdata in active_pages.items():
                try:
                    await pdata["page"].close()
                except Exception:
                    pass
                try:
                    await pdata["context"].close()
                except Exception:
                    pass
            await bm.stop()

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
                emails_sent = 0  # count for THIS campaign only (MAX cap)
                # Warmup level: existing accounts start at their maturity level
                # so they immediately get fast delays (1min for warmed accounts)
                warmup_level = account_data.get("prior_sends", 0)

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
                        # No more recipients -> campaign complete
                        logger.info(f"Blitz send[{worker_id}]: no more recipients")
                        await self.stop("All recipients sent")
                        break

                    # Get template - ONE-TIME USE (like links, each template burns after use)
                    template = db.query(CampaignTemplate).filter(
                        CampaignTemplate.campaign_id == self.campaign_id,
                        CampaignTemplate.active == True  # noqa
                    ).first()  # sequential, not random
                    if not template:
                        # Wait for user to add templates (hot-reload)
                        logger.warning(f"Blitz send[{worker_id}]: no active templates, waiting for reload...")
                        for _ in range(RESOURCE_WAIT_TIMEOUT // 10):
                            await asyncio.sleep(10)
                            if self._stop_event.is_set():
                                break
                            template = db.query(CampaignTemplate).filter(
                                CampaignTemplate.campaign_id == self.campaign_id,
                                CampaignTemplate.active == True
                            ).first()
                            if template:
                                logger.info(f"Blitz send[{worker_id}]: templates reloaded")
                                break
                        if not template:
                            await self.stop("No active templates (waited 5 min)")
                            break

                    # Lock template - mark inactive BEFORE send to prevent other threads using it
                    template_id = template.id
                    template.active = False
                    template.use_count = (template.use_count or 0) + 1
                    db.commit()

                    # Get ESP link
                    link = db.query(CampaignLink).filter(
                        CampaignLink.campaign_id == self.campaign_id,
                        CampaignLink.active == True,  # noqa
                        CampaignLink.use_count < CampaignLink.max_uses
                    ).order_by(CampaignLink.use_count.asc()).first()

                    if not link:
                        # Wait for user to add more links (hot-reload)
                        logger.warning(f"Blitz send[{worker_id}]: all links exhausted, waiting for reload...")
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
                                logger.info(f"Blitz send[{worker_id}]: links reloaded ({link.esp_url[:40]}...)")
                                break
                        if not link:
                            await self.stop("All links exhausted (waited 5 min)")
                            break

                    # Randomize link (but DON'T increment use_count yet!)
                    rand_hash = ''.join(random.choices(
                        string.ascii_letters + string.digits, k=6
                    ))
                    link_url = f"{link.esp_url}#{rand_hash}"
                    link_id = link.id  # save for post-send update

                    # Render template with BASIC/VIP variables
                    subject = template.subject
                    body = template.body_html

                    # ═══ BASIC variables (always available) ═══
                    # {{USERNAME}} = part before @ in recipient email
                    to_email_str = recipient.email or ""
                    username = to_email_str.split("@")[0] if "@" in to_email_str else to_email_str
                    subject = subject.replace("{{USERNAME}}", username)
                    body = body.replace("{{USERNAME}}", username)

                    # ═══ VIP variables ═══
                    # {{NAME}} = first_name from VIP db, falls back to username if BASIC
                    to_name = getattr(recipient, 'first_name', '') or ''
                    if not to_name:
                        to_name = username  # BASIC fallback: {{NAME}} = username
                    subject = subject.replace("{{NAME}}", to_name)
                    body = body.replace("{{NAME}}", to_name)

                    # Legacy compatibility
                    subject = subject.replace("{{FIRSTNAME}}", to_name)
                    body = body.replace("{{FIRSTNAME}}", to_name)
                    subject = subject.replace("{first_name}", from_name)
                    body = body.replace("{first_name}", from_name)

                    # Date
                    date_str = datetime.utcnow().strftime("%d/%m/%Y")
                    subject = subject.replace("{{DATE}}", date_str).replace("{date}", date_str)
                    body = body.replace("{{DATE}}", date_str).replace("{date}", date_str)

                    # ═══ LINK variable ═══
                    # {{LINK}} = ESP link with random hash
                    body = body.replace("{{LINK}}", link_url)
                    subject = subject.replace("{{LINK}}", link_url)
                    # Legacy
                    body = body.replace("{link}", link_url)

                    # Lock recipient to prevent double-send by other threads
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

                    # ═══ Process result - ONLY count resources on SUCCESS ═══
                    if result == SendResult.OK:
                        recipient.result = "ok"
                        emails_sent += 1
                        warmup_level += 1
                        consecutive_errors = 0

                        # NOW increment link usage (only on success!)
                        link = db.query(CampaignLink).filter(
                            CampaignLink.id == link_id
                        ).first()
                        if link:
                            link.use_count += 1
                            if link.use_count >= link.max_uses:
                                link.active = False

                        # Template already burned (active=False before send) - no action needed

                        # Update campaign stats - only real successes
                        campaign = db.query(Campaign).filter(
                            Campaign.id == self.campaign_id
                        ).first()
                        if campaign:
                            campaign.total_sent = (campaign.total_sent or 0) + 1

                        # Track account maturity for future warmup skip
                        if account_data.get("account_id"):
                            acc = db.query(Account).filter(
                                Account.id == account_data["account_id"]
                            ).first()
                            if acc:
                                acc.total_emails_sent = (acc.total_emails_sent or 0) + 1
                                acc.emails_sent_today = (acc.emails_sent_today or 0) + 1

                        db.commit()
                        logger.debug(
                            f"Blitz send[{worker_id}] {email} -> {recipient.email} "
                            f"({emails_sent}/{MAX_EMAILS_PER_ACCOUNT})"
                        )

                    elif result == SendResult.RATE_LIMIT:
                        # Rate limited - undo recipient + template, SWITCH to new account
                        recipient.sent = False
                        recipient.sent_at = None
                        recipient.result = None
                        # Unlock template (wasn't delivered)
                        t = db.query(CampaignTemplate).filter(CampaignTemplate.id == template_id).first()
                        if t:
                            t.active = True
                            t.use_count = max((t.use_count or 1) - 1, 0)
                        campaign = db.query(Campaign).filter(
                            Campaign.id == self.campaign_id
                        ).first()
                        if campaign:
                            campaign.accounts_dead = (campaign.accounts_dead or 0) + 1
                        db.commit()
                        logger.warning(
                            f"Blitz send[{worker_id}] {email} RATE LIMITED -> switching account"
                        )
                        break  # exit inner loop -> get NEW account from queue

                    elif result in (SendResult.AUTH_FAIL, SendResult.SUSPENDED):
                        # Account is dead - undo recipient + template, DON'T burn
                        recipient.sent = False
                        recipient.sent_at = None
                        recipient.result = None
                        # Unlock template
                        t = db.query(CampaignTemplate).filter(CampaignTemplate.id == template_id).first()
                        if t:
                            t.active = True
                            t.use_count = max((t.use_count or 1) - 1, 0)
                        campaign = db.query(Campaign).filter(
                            Campaign.id == self.campaign_id
                        ).first()
                        if campaign:
                            campaign.total_errors = (campaign.total_errors or 0) + 1
                            campaign.accounts_dead = (campaign.accounts_dead or 0) + 1
                        db.commit()
                        logger.warning(
                            f"Blitz send[{worker_id}] {email} DEAD: {result} - {detail[:80]}"
                        )
                        break  # exit inner loop, get new account

                    elif result == SendResult.BOUNCE:
                        # Bad recipient address - mark as bounce, DON'T burn link
                        recipient.result = "bounce"
                        campaign = db.query(Campaign).filter(
                            Campaign.id == self.campaign_id
                        ).first()
                        if campaign:
                            campaign.total_errors = (campaign.total_errors or 0) + 1
                        db.commit()
                        consecutive_errors = 0  # bounce is recipient issue, not account

                    elif result == SendResult.NETWORK:
                        # Network issue - undo everything including template
                        recipient.sent = False
                        recipient.sent_at = None
                        recipient.result = None
                        t = db.query(CampaignTemplate).filter(CampaignTemplate.id == template_id).first()
                        if t:
                            t.active = True
                            t.use_count = max((t.use_count or 1) - 1, 0)
                        db.commit()
                        consecutive_errors += 1
                        await asyncio.sleep(10)

                    else:
                        # Unknown error - mark failed, DON'T burn link
                        recipient.result = "error"
                        campaign = db.query(Campaign).filter(
                            Campaign.id == self.campaign_id
                        ).first()
                        if campaign:
                            campaign.total_errors = (campaign.total_errors or 0) + 1
                        db.commit()
                        consecutive_errors += 1

                    # Progressive warmup delay - uses warmup_level (includes prior sends)
                    delay = get_warmup_delay(warmup_level)
                    if warmup_level <= len(WARMUP_DELAYS):
                        logger.debug(
                            f"Blitz send[{worker_id}] {email}: warmup delay "
                            f"{delay:.0f}s (level={warmup_level}, sent={emails_sent})"
                        )
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
        """Periodic resource check - auto-pause on critical deficit."""
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
                        await self.stop("All recipients sent - campaign complete")
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
