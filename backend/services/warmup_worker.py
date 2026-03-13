"""
Leomail v4 - Warm-up Engine Worker (Browser-Based)
Progressive email sending + inbox interactions to build sender reputation.
Sends via browser UI (like Campaign engine) for authentic email headers.
Supports peer-to-peer warming (accounts send to each other).
Inbox actions: reply, star, mark important, rescue from spam.
"""
import asyncio
import os
import random
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger
from sqlalchemy.orm import Session

from ..models import Account, AccountStatus, WarmupEmail
from ..config import get_warmup_config
from ..services.engine_manager import EngineManager, EngineType


# ── Warmup settings (user-configurable) ───────────────────────────────────────

@dataclass
class WarmupSettings:
    """User-configurable warmup parameters. Passed from router."""
    warmup_days: int = 30           # Total warmup duration
    emails_per_day: int = 0         # 0 = auto (phase-based progressive)
    enable_replies: bool = True     # Reply to received warmup emails
    enable_starring: bool = True    # Star/important random emails
    enable_spam_rescue: bool = True # Check spam folder, move to inbox
    reply_chance: float = 0.5       # Probability of replying to each email
    star_chance: float = 0.3        # Probability of starring each email
    important_chance: float = 0.15  # Probability of marking important
    spam_check_chance: float = 0.4  # Probability of checking spam folder


# ── Warm-up email subjects and bodies ──────────────────────────────────────────

WARMUP_SUBJECTS = [
    "Quick question about the project",
    "Following up on our call",
    "Re: Meeting tomorrow",
    "Checking in",
    "Great article I found",
    "Weekend plans?",
    "That document you asked about",
    "Thoughts on this?",
    "Re: Budget review",
    "Coffee next week?",
    "Happy Monday!",
    "Thank you for the update",
    "Agenda for tomorrow",
    "Can you review this?",
    "FYI - new schedule",
    "Quick heads up",
    "Confirmed for Thursday",
    "Running a bit late",
    "Got your message",
    "Sounds good!",
]

WARMUP_BODIES = [
    "Hi! Just wanted to follow up on what we discussed. Let me know your thoughts when you get a chance.",
    "Hey, I saw this and thought of you. Hope all is well!",
    "Thanks for getting back to me so quickly. I'll review everything and circle back tomorrow.",
    "Just a quick note - I'll be on a call most of the afternoon. Can we catch up later this week?",
    "Perfect, that works for me. See you then!",
    "I just sent over the updated document. Let me know if you have any questions.",
    "Thanks for the heads up. I'll make sure to review it before our meeting.",
    "Sounds great! Looking forward to it.",
    "Good morning! Just checking in to see if you need anything from me on this.",
    "That's a great point. I'll think about it and get back to you.",
    "Hey! Quick question - did you end up going with option A or B?",
    "I appreciate the update. Everything looks good on my end.",
    "Just wanted to say thank you for all your help this week.",
    "No worries at all! Take your time and let me know when you're ready.",
    "I'll forward you the details later today. Have a great morning!",
]

REPLY_BODIES = [
    "Got it, thanks!",
    "Makes sense. I'll take a look.",
    "Sounds good to me!",
    "Appreciated, thank you.",
    "Will do! Talk soon.",
    "Perfect, works for me.",
    "Thanks for letting me know.",
    "Great, I'll handle it from here.",
    "Noted! Talk to you later.",
    "No problem at all.",
]

WARMUP_TOKEN_RE = re.compile(r"\[lmw:([a-z0-9]{6,12})\]", re.IGNORECASE)


def _normalize_subject(subject: str | None) -> str:
    return " ".join((subject or "").strip().split()).lower()


def _make_warmup_token(length: int = 6) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(random.choice(alphabet) for _ in range(length))


def _decorate_warmup_subject(base_subject: str) -> str:
    token = _make_warmup_token()
    return f"{base_subject} [lmw:{token}]"


def _extract_warmup_token(subject: str | None) -> str:
    match = WARMUP_TOKEN_RE.search(subject or "")
    return (match.group(1) if match else "").lower()


def _record_warmup_send(db: Session, sender_account_id: int, receiver_account_id: int, subject: str):
    """Persist a warmup send so later inbox/spam/reply actions can update its fate."""
    if not sender_account_id or not receiver_account_id or not subject:
        return
    db.add(
        WarmupEmail(
            sender_account_id=sender_account_id,
            receiver_account_id=receiver_account_id,
            subject=subject[:250],
            delivery_status="pending",
        )
    )
    db.flush()


def _match_recent_warmup_email(
    db: Session,
    receiver_account_id: int,
    subject: str,
    statuses: tuple[str, ...] = ("pending", "inbox", "spam", "not_found"),
) -> WarmupEmail | None:
    """Best-effort match of a tracked warmup email by receiver + normalized subject."""
    subject_norm = _normalize_subject(subject)
    subject_token = _extract_warmup_token(subject)
    if not receiver_account_id or not subject_norm:
        return None

    candidates = (
        db.query(WarmupEmail)
        .filter(
            WarmupEmail.receiver_account_id == receiver_account_id,
            WarmupEmail.delivery_status.in_(statuses),
        )
        .order_by(WarmupEmail.sent_at.desc())
        .limit(25)
        .all()
    )
    for candidate in candidates:
        if subject_token and _extract_warmup_token(candidate.subject) == subject_token:
            return candidate
        if _normalize_subject(candidate.subject) == subject_norm:
            return candidate
    return None


def _mark_warmup_delivery(db: Session, receiver_account_id: int, subject: str, status: str) -> bool:
    tracked = _match_recent_warmup_email(db, receiver_account_id, subject)
    if not tracked:
        return False
    tracked.delivery_status = status
    tracked.checked_at = datetime.utcnow()
    return True


def _mark_warmup_reply(db: Session, receiver_account_id: int, subject: str) -> bool:
    tracked = _match_recent_warmup_email(db, receiver_account_id, subject, statuses=("pending", "inbox", "spam"))
    if not tracked:
        return False
    tracked.delivery_status = "inbox"
    tracked.checked_at = datetime.utcnow()
    tracked.replied = True
    tracked.replied_at = datetime.utcnow()
    return True


# ── Phase calculation (dynamic, based on user settings) ──────────────────────

PHASE_STATUSES = [
    AccountStatus.PHASE_1,
    AccountStatus.PHASE_2,
    AccountStatus.PHASE_3,
    AccountStatus.PHASE_4,
    AccountStatus.PHASE_5,
]


def get_phase_for_day(day: int, settings: WarmupSettings = None) -> tuple:
    """
    Returns (min_emails, max_emails, status) for a given warmup day.
    Uses user-configurable total_days instead of hardcoded 30.
    """
    if settings is None:
        settings = WarmupSettings()

    total_days = max(5, settings.warmup_days)  # Minimum 5 days

    if day > total_days:
        return 0, 0, AccountStatus.WARMED

    # Divide total_days into 5 equal phases
    phase_length = max(1, total_days // 5)
    phase_num = min(5, (day - 1) // phase_length + 1)
    phase_idx = phase_num - 1
    status = PHASE_STATUSES[phase_idx]

    # If user set explicit emails_per_day, use that as max for current phase
    if settings.emails_per_day > 0:
        max_for_phase = settings.emails_per_day
        # Progressive: phase 1 = 20%, phase 5 = 100%
        phase_pct = phase_num / 5
        min_emails = max(1, int(max_for_phase * max(0.1, phase_pct - 0.2)))
        max_emails = max(min_emails + 1, int(max_for_phase * phase_pct))
        return min_emails, max_emails, status

    # Auto mode: use config schedule or defaults
    config = get_warmup_config()
    schedule = config.get("schedule", {})

    # Default progressive schedule
    defaults = [
        {"min": 1, "max": 3},    # Phase 1
        {"min": 3, "max": 8},    # Phase 2
        {"min": 5, "max": 15},   # Phase 3
        {"min": 10, "max": 30},  # Phase 4
        {"min": 15, "max": 50},  # Phase 5
    ]

    phase_keys = ["day_1_3", "day_4_7", "day_8_14", "day_15_21", "day_22_30"]
    phase_config = schedule.get(phase_keys[phase_idx], defaults[phase_idx])
    return phase_config["min"], phase_config["max"], status


# ── Browser-based send ─────────────────────────────────────────────────────────

async def send_warmup_email_browser(
    page,
    provider: str,
    to_email: str,
    subject: str = None,
    body: str = None,
    is_reply: bool = False,
) -> tuple[bool, str]:
    """
    Send a single warm-up email via browser UI.
    Uses the shared browser_mail_sender module.
    """
    from ..modules.browser_mail_sender import browser_compose_send

    subject = subject or random.choice(WARMUP_SUBJECTS)
    body = body or random.choice(REPLY_BODIES if is_reply else WARMUP_BODIES)

    if is_reply:
        subject = f"Re: {subject}"

    try:
        await browser_compose_send(page, provider, to_email, subject, body)
        logger.debug(f"Warmup email sent via browser: -> {to_email}")
        return True, ""
    except Exception as e:
        logger.warning(f"Browser warmup send failed -> {to_email}: {e}")
        return False, str(e)


# ── Main warm-up worker ───────────────────────────────────────────────────────

async def warmup_single_account(
    account: Account,
    peer_accounts: list[Account],
    db: Session,
    cancel_event: threading.Event,
    settings: WarmupSettings = None,
) -> dict:
    """
    Warm up a single account for one session using browser-based sending.

    Opens a browser session, navigates to webmail, sends peer-to-peer
    warmup emails, then performs inbox interactions (reply, star, spam rescue).

    Returns: {"sent": N, "received": N, "replied": N, "starred": N, "spam_rescued": N, "errors": N}
    """
    from ..modules.browser_manager import BrowserManager
    from ..modules.browser_mail_sender import MAIL_URLS, is_login_page
    from ..modules.browser_mail_actions import (
        read_inbox_emails, reply_to_email,
        mark_as_starred, mark_as_important,
        rescue_from_spam,
    )

    if settings is None:
        settings = WarmupSettings()

    result = {"sent": 0, "received": 0, "replied": 0, "starred": 0, "spam_rescued": 0, "errors": 0}

    if cancel_event.is_set():
        return result

    provider = account.provider or "outlook"
    account_proxy = getattr(account, "proxy", None)
    account_geo = getattr(account, "geo", None)

    # Calculate warmup day
    if not account.warmup_started_at:
        account.warmup_started_at = datetime.utcnow()
        account.warmup_day = 1
    else:
        delta = (datetime.utcnow() - account.warmup_started_at).days + 1
        account.warmup_day = delta

    day = account.warmup_day
    min_emails, max_emails, target_status = get_phase_for_day(day, settings)

    # Past total warmup days -> mark as warmed
    if day > settings.warmup_days:
        account.status = AccountStatus.WARMED
        try:
            db.commit()
        except Exception:
            pass
        logger.info(f"[OK] {account.email} fully warmed (day {day}/{settings.warmup_days})")
        return result

    # Update status to current phase
    account.status = target_status

    # How many emails to send this session
    already_sent = account.emails_sent_today or 0
    target_today = random.randint(min_emails, max_emails)
    remaining = max(0, target_today - already_sent)

    if remaining == 0:
        logger.debug(f"{account.email}: already sent {already_sent}/{target_today} today")
        try:
            db.commit()
        except Exception:
            pass
        return result

    logger.info(
        f"[OK] Warming {account.email} (day {day}/{settings.warmup_days}, "
        f"phase {target_status.value}): {remaining} emails to send"
    )

    config = get_warmup_config()
    delay_min = config.get("human_delay_min_sec", 30)
    delay_max = config.get("human_delay_max_sec", 120)

    # ── Open browser session for this account ──
    bm = None
    context = None
    page = None

    try:
        bm = BrowserManager(headless=True)
        await bm.start()

        # Load saved session + fingerprint (profile persistence)
        try:
            context, session_path = await bm.load_session_context(
                account_id=account.id,
                proxy=account_proxy,
                geo=account_geo,
            )
        except Exception as e:
            logger.warning(f"[WARN] {account.email}: session load failed: {e}")
            context = await bm.create_context(
                proxy=account_proxy,
                geo=account_geo,
                account_id=account.id,
            )

        page = await context.new_page()

        # Navigate to webmail
        mail_url = MAIL_URLS.get(provider, "https://outlook.live.com/mail")
        try:
            await page.goto(mail_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(random.uniform(3, 6))
        except Exception as e:
            logger.error(f"[ERR] {account.email}: failed to open {mail_url}: {e}")
            result["errors"] += 1
            return result

        # Check if session is valid (not redirected to login)
        if is_login_page(page.url):
            logger.info(f"[Warmup] {account.email}: session expired, attempting re-login...")
            from ..modules.browser_relogin import browser_relogin
            relogin_ok = await browser_relogin(page, provider, account.email, account.password)
            if relogin_ok:
                # Save new session for future use
                try:
                    await bm.save_session(context, account.id)
                    logger.info(f"[Warmup] {account.email}: re-login successful, session saved")
                except Exception as se:
                    logger.warning(f"[Warmup] {account.email}: session save after re-login failed: {se}")
            else:
                logger.warning(f"[Warmup] {account.email}: re-login failed, skipping")
                account.health_score = max(0, (account.health_score or 100) - 20)
                try:
                    db.commit()
                except Exception:
                    pass
                result["errors"] += 1
                return result

        # ── Send emails to peers (peer-to-peer warming) ──
        for i in range(remaining):
            if cancel_event.is_set():
                break

            # Pick random peer to send to
            if peer_accounts:
                peer = random.choice(peer_accounts)
                to_email = peer.email
            else:
                logger.warning(f"No peer accounts for warming {account.email}")
                break

            # Human-like delay between sends (longer than campaign — warmup must be slow)
            if i > 0:
                await asyncio.sleep(random.uniform(delay_min, delay_max))

            # Send email via browser
            is_reply = random.random() < 0.3  # 30% chance of reply-style
            subject = _decorate_warmup_subject(random.choice(WARMUP_SUBJECTS))
            body = random.choice(REPLY_BODIES if is_reply else WARMUP_BODIES)
            if is_reply:
                subject = f"Re: {subject}"

            success, send_error = await send_warmup_email_browser(
                page=page,
                provider=provider,
                to_email=to_email,
                subject=subject,
                body=body,
                is_reply=is_reply,
            )

            if success:
                result["sent"] += 1
                account.emails_sent_today = (account.emails_sent_today or 0) + 1
                account.total_emails_sent = (account.total_emails_sent or 0) + 1
                account.last_email_sent_at = datetime.utcnow()
                # Track success in ErrorHandler
                try:
                    from ..services.error_handler import error_handler
                    error_handler.record_sent(account.email)
                except Exception:
                    pass
                _record_warmup_send(db, account.id, peer.id, subject)
            else:
                result["errors"] += 1
                # Classify error through ErrorHandler
                try:
                    from ..services.error_handler import error_handler
                    handled = error_handler.handle_error(
                        send_error or "warmup_send_failed", account.email, to_email
                    )
                    if error_handler.is_bounce_type(handled.error_type):
                        account.bounces = (account.bounces or 0) + 1
                except Exception:
                    pass
                # If too many errors, reduce health score
                if result["errors"] >= 3:
                    account.health_score = max(0, (account.health_score or 100) - 10)
                    logger.warning(f"[WARN] {account.email}: health score dropped to {account.health_score}")
                    break

        # ── Phase 2: Inbox interactions (replies, stars, spam rescue) ──
        if not cancel_event.is_set() and day >= 2:
            try:
                # 1. Read inbox emails
                inbox_emails = await read_inbox_emails(page, provider, max_emails=random.randint(2, 4))
                result["received"] += len(inbox_emails)
                for email_info in inbox_emails:
                    _mark_warmup_delivery(db, account.id, email_info.get("subject"), "inbox")

                # 2. Reply to warmup emails
                if settings.enable_replies and inbox_emails:
                    reply_count = 0
                    for email_info in inbox_emails:
                        if cancel_event.is_set():
                            break
                        if random.random() < settings.reply_chance and reply_count < 2:
                            await asyncio.sleep(random.uniform(5, 15))
                            replied = await reply_to_email(
                                page, provider, email_info["index"],
                                random.choice(REPLY_BODIES),
                            )
                            if replied:
                                result["replied"] += 1
                                reply_count += 1
                                account.emails_sent_today = (account.emails_sent_today or 0) + 1
                                account.total_emails_sent = (account.total_emails_sent or 0) + 1
                                _mark_warmup_reply(db, account.id, email_info.get("subject"))

                # 3. Star random emails
                if settings.enable_starring and inbox_emails:
                    for email_info in inbox_emails:
                        if random.random() < settings.star_chance:
                            starred = await mark_as_starred(page, provider, email_info["index"])
                            if starred:
                                result["starred"] += 1
                        if random.random() < settings.important_chance:
                            await mark_as_important(page, provider, email_info["index"])

                # 4. Spam rescue (check spam folder, move warmup emails to inbox)
                if settings.enable_spam_rescue and random.random() < settings.spam_check_chance:
                    await asyncio.sleep(random.uniform(3, 8))
                    rescued_emails = await rescue_from_spam(page, provider, max_emails=random.randint(1, 3))
                    result["spam_rescued"] += len(rescued_emails)
                    for email_info in rescued_emails:
                        _mark_warmup_delivery(db, account.id, email_info.get("subject"), "spam")

            except Exception as e:
                logger.warning(f"[WARN] {account.email} inbox actions failed: {e}")
                result["errors"] += 1

        # Save browser session for next time
        try:
            session_path = bm.get_session_path(account.id)
            os.makedirs(os.path.dirname(session_path), exist_ok=True)
            await bm.save_session(context, account.id)
        except Exception as e:
            logger.debug(f"Failed to save session for {account.email}: {e}")

    except Exception as e:
        logger.error(f"[ERR] {account.email} warmup browser error: {e}")
        result["errors"] += 1

    finally:
        # Clean shutdown — close browser resources
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

    account.last_active = datetime.utcnow()
    try:
        db.commit()
    except Exception:
        pass

    logger.info(
        f"[OK] {account.email} warmup session: sent={result['sent']}, "
        f"replied={result['replied']}, starred={result['starred']}, "
        f"spam_rescued={result['spam_rescued']}, errors={result['errors']}"
    )
    return result


# ── Batch warm-up runner ──────────────────────────────────────────────────────

async def run_warmup_batch(
    accounts: list[Account],
    db: Session,
    cancel_event: threading.Event,
    max_threads: int = 3,
    settings: WarmupSettings = None,
) -> dict:
    """
    Run warm-up for a batch of accounts using browser-based sending.
    Accounts warm each other (peer-to-peer) + inbox interactions.
    Default max_threads=3 (each opens a browser — RAM-aware).

    Returns: {"total_sent": N, "total_received": N, "total_replied": N, ... "accounts_processed": N}
    """
    from ..database import SessionLocal
    from ..services.engine_manager import engine_manager as _engine_mgr

    if settings is None:
        settings = WarmupSettings()
    _engine_mgr.start_engine(EngineType.WARMUP, max_threads, len(accounts))

    totals = {
        "total_sent": 0, "total_received": 0, "total_replied": 0,
        "total_starred": 0, "total_spam_rescued": 0,
        "total_errors": 0, "accounts_processed": 0,
    }

    # Collect account IDs for per-task session isolation
    account_ids = [acc.id for acc in accounts if acc.status != AccountStatus.WARMED]
    all_account_ids = [acc.id for acc in accounts]

    # Reset daily counters if new day
    for acc in accounts:
        if acc.last_email_sent_at:
            if acc.last_email_sent_at.date() < datetime.utcnow().date():
                acc.emails_sent_today = 0
    try:
        db.commit()
    except Exception:
        pass

    # Process with semaphore (limit concurrent browsers for RAM)
    semaphore = asyncio.Semaphore(max_threads)
    totals_lock = asyncio.Lock()

    async def process_one(account_id: int):
        async with semaphore:
            if cancel_event.is_set():
                return
            # Each task gets its own DB session (SQLAlchemy is NOT thread-safe)
            task_db = SessionLocal()
            try:
                account = task_db.query(Account).get(account_id)
                if not account:
                    return
                # Load peer accounts in this session
                peers = task_db.query(Account).filter(
                    Account.id.in_(all_account_ids),
                    Account.id != account_id,
                ).all()
                result = await warmup_single_account(account, peers, task_db, cancel_event, settings)
                async with totals_lock:
                    totals["total_sent"] += result["sent"]
                    totals["total_received"] += result["received"]
                    totals["total_replied"] += result["replied"]
                    totals["total_starred"] += result["starred"]
                    totals["total_spam_rescued"] += result["spam_rescued"]
                    totals["total_errors"] += result["errors"]
                    totals["accounts_processed"] += 1
                _engine_mgr.get_engine(EngineType.WARMUP).increment_completed()
            except Exception as e:
                logger.error(f"[Warmup] process_one error for account {account_id}: {e}")
            finally:
                task_db.close()

    tasks = [process_one(aid) for aid in account_ids]
    await asyncio.gather(*tasks, return_exceptions=True)

    _engine_mgr.finish_engine(EngineType.WARMUP)
    logger.info(f"[OK] Warmup batch complete: {totals}")
    return totals
