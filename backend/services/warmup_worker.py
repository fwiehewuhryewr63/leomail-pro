"""
Leomail v4 - Warm-up Engine Worker
Progressive email sending to build sender reputation.
Supports peer-to-peer warming (accounts send to each other) and external warming.
"""
import asyncio
import random
import smtplib
import imaplib
import email
import threading
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from loguru import logger
from sqlalchemy.orm import Session

from ..models import Account, AccountStatus
from ..config import get_warmup_config
from ..services.engine_manager import EngineManager, EngineType


# ── SMTP/IMAP server configs per provider ──────────────────────────────────────

PROVIDER_CONFIGS = {
    "gmail": {
        "imap": ("imap.gmail.com", 993),
        "smtp": ("smtp.gmail.com", 587),
        "smtp_ssl": False,
    },
    "outlook": {
        "imap": ("outlook.office365.com", 993),
        "smtp": ("smtp.office365.com", 587),
        "smtp_ssl": False,
    },
    "hotmail": {
        "imap": ("outlook.office365.com", 993),
        "smtp": ("smtp.office365.com", 587),
        "smtp_ssl": False,
    },
    "yahoo": {
        "imap": ("imap.mail.yahoo.com", 993),
        "smtp": ("smtp.mail.yahoo.com", 587),
        "smtp_ssl": False,
    },
    "protonmail": {
        "imap": ("127.0.0.1", 1143),  # ProtonMail Bridge required
        "smtp": ("127.0.0.1", 1025),
        "smtp_ssl": False,
    },
    "tuta": {
        # Tuta doesn't support standard IMAP/SMTP - skip for warmup
        "imap": None,
        "smtp": None,
        "smtp_ssl": False,
    },
}

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


# ── Phase mapping ──────────────────────────────────────────────────────────────

PHASE_MAP = {
    "day_1_3": (1, 3, AccountStatus.PHASE_1),
    "day_4_7": (4, 7, AccountStatus.PHASE_2),
    "day_8_14": (8, 14, AccountStatus.PHASE_3),
    "day_15_21": (15, 21, AccountStatus.PHASE_4),
    "day_22_30": (22, 30, AccountStatus.PHASE_5),
}


def get_phase_for_day(day: int) -> tuple:
    """Returns (min_emails, max_emails, status) for a given warmup day."""
    config = get_warmup_config()
    schedule = config.get("schedule", {})

    for phase_key, (day_min, day_max, status) in PHASE_MAP.items():
        if day_min <= day <= day_max:
            phase_config = schedule.get(phase_key, {"min": 1, "max": 3})
            return phase_config["min"], phase_config["max"], status

    # Day 30+ - fully warmed
    return 0, 0, AccountStatus.WARMED


# ── SMTP send ──────────────────────────────────────────────────────────────────

def send_warmup_email(
    from_email: str,
    from_password: str,
    to_email: str,
    provider: str,
    subject: str = None,
    body: str = None,
    is_reply: bool = False,
) -> bool:
    """Send a single warm-up email via SMTP."""
    config = PROVIDER_CONFIGS.get(provider)
    if not config or not config.get("smtp"):
        logger.debug(f"No SMTP config for {provider}, skipping")
        return False

    smtp_host, smtp_port = config["smtp"]
    subject = subject or random.choice(WARMUP_SUBJECTS)
    body = body or random.choice(REPLY_BODIES if is_reply else WARMUP_BODIES)

    if is_reply:
        subject = f"Re: {subject}"

    msg = MIMEMultipart("alternative")
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid(domain=from_email.split("@")[1])

    # Plain text + minimal HTML for realism
    msg.attach(MIMEText(body, "plain"))
    html_body = f"<html><body><p>{body}</p></body></html>"
    msg.attach(MIMEText(html_body, "html"))

    try:
        if config.get("smtp_ssl"):
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
            server.ehlo()
            server.starttls()
            server.ehlo()

        server.login(from_email, from_password)
        server.sendmail(from_email, to_email, msg.as_string())
        server.quit()
        logger.debug(f"Warmup email sent: {from_email} -> {to_email}")
        return True
    except smtplib.SMTPAuthenticationError as e:
        logger.warning(f"SMTP auth failed for {from_email}: {e}")
        return False
    except Exception as e:
        logger.error(f"SMTP error {from_email}: {e}")
        return False


# ── IMAP check inbox ───────────────────────────────────────────────────────────

def check_inbox_and_reply(
    account_email: str,
    account_password: str,
    provider: str,
) -> int:
    """Check inbox and mark warmup emails as read. Returns count of new emails."""
    config = PROVIDER_CONFIGS.get(provider)
    if not config or not config.get("imap"):
        return 0

    imap_host, imap_port = config["imap"]
    try:
        mail = imaplib.IMAP4_SSL(imap_host, imap_port)
        mail.login(account_email, account_password)
        mail.select("INBOX")

        # Search for unseen emails
        _, message_numbers = mail.search(None, "UNSEEN")
        count = len(message_numbers[0].split()) if message_numbers[0] else 0

        # Mark as read by fetching
        if count > 0:
            for num in message_numbers[0].split()[:10]:  # limit to 10
                mail.fetch(num, "(RFC822)")

        mail.logout()
        return count
    except Exception as e:
        logger.debug(f"IMAP check failed for {account_email}: {e}")
        return 0


# ── Verify IMAP login ─────────────────────────────────────────────────────────

def verify_imap_login(account_email: str, account_password: str, provider: str) -> bool:
    """Quick IMAP login check to verify account is alive."""
    config = PROVIDER_CONFIGS.get(provider)
    if not config or not config.get("imap"):
        return True  # Skip for providers without IMAP

    imap_host, imap_port = config["imap"]
    try:
        mail = imaplib.IMAP4_SSL(imap_host, imap_port)
        mail.login(account_email, account_password)
        mail.logout()
        return True
    except Exception:
        return False


# ── Main warm-up worker ───────────────────────────────────────────────────────

async def warmup_single_account(
    account: Account,
    peer_accounts: list[Account],
    db: Session,
    cancel_event: threading.Event,
) -> dict:
    """
    Warm up a single account for one session.
    
    Returns: {"sent": N, "received": N, "errors": N}
    """
    result = {"sent": 0, "received": 0, "errors": 0}

    if cancel_event.is_set():
        return result

    provider = account.provider or "outlook"

    # Calculate warmup day
    if not account.warmup_started_at:
        account.warmup_started_at = datetime.utcnow()
        account.warmup_day = 1
    else:
        delta = (datetime.utcnow() - account.warmup_started_at).days + 1
        account.warmup_day = delta

    day = account.warmup_day
    min_emails, max_emails, target_status = get_phase_for_day(day)

    # Day 30+ -> mark as warmed
    if day > 30:
        account.status = AccountStatus.WARMED
        try:
            db.commit()
        except Exception:
            pass
        logger.info(f"[OK] {account.email} fully warmed (day {day})")
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

    logger.info(f"[OK] Warming {account.email} (day {day}, phase {target_status.value}): {remaining} emails to send")

    config = get_warmup_config()
    delay_min = config.get("human_delay_min_sec", 2)
    delay_max = config.get("human_delay_max_sec", 15)

    # Send emails to peers (peer-to-peer warming)
    for i in range(remaining):
        if cancel_event.is_set():
            break

        # Pick random peer to send to
        if peer_accounts:
            peer = random.choice(peer_accounts)
            to_email = peer.email
        else:
            # No peers - skip
            logger.warning(f"No peer accounts for warming {account.email}")
            break

        # Human-like delay between sends
        await asyncio.sleep(random.uniform(delay_min, delay_max))

        # Send email
        is_reply = random.random() < 0.3  # 30% chance of reply-style
        success = await asyncio.to_thread(
            send_warmup_email,
            from_email=account.email,
            from_password=account.password,
            to_email=to_email,
            provider=provider,
            is_reply=is_reply,
        )

        if success:
            result["sent"] += 1
            account.emails_sent_today = (account.emails_sent_today or 0) + 1
            account.total_emails_sent = (account.total_emails_sent or 0) + 1
            account.last_email_sent_at = datetime.utcnow()
        else:
            result["errors"] += 1
            account.bounces = (account.bounces or 0) + 1
            # If too many errors, reduce health score
            if result["errors"] >= 3:
                account.health_score = max(0, (account.health_score or 100) - 10)
                logger.warning(f"[WARN] {account.email}: health score dropped to {account.health_score}")
                break

    # Check inbox (read received warmup emails)
    received = await asyncio.to_thread(
        check_inbox_and_reply,
        account_email=account.email,
        account_password=account.password,
        provider=provider,
    )
    result["received"] = received

    account.last_active = datetime.utcnow()
    try:
        db.commit()
    except Exception:
        pass

    logger.info(
        f"[OK] {account.email} warmup session: sent={result['sent']}, "
        f"received={result['received']}, errors={result['errors']}"
    )
    return result


# ── Batch warm-up runner ──────────────────────────────────────────────────────

async def run_warmup_batch(
    accounts: list[Account],
    db: Session,
    cancel_event: threading.Event,
    max_threads: int = 5,
) -> dict:
    """
    Run warm-up for a batch of accounts.
    Accounts warm each other (peer-to-peer).
    
    Returns: {"total_sent": N, "total_received": N, "total_errors": N, "accounts_processed": N}
    """
    engine_manager = EngineManager()
    engine_manager.start_engine(EngineType.WARMUP, len(accounts))

    totals = {"total_sent": 0, "total_received": 0, "total_errors": 0, "accounts_processed": 0}

    # Reset daily counters if new day
    for acc in accounts:
        if acc.last_email_sent_at:
            if acc.last_email_sent_at.date() < datetime.utcnow().date():
                acc.emails_sent_today = 0
    try:
        db.commit()
    except Exception:
        pass

    # Process in chunks (pseudo-parallel via semaphore)
    semaphore = asyncio.Semaphore(max_threads)

    async def process_one(account: Account):
        async with semaphore:
            if cancel_event.is_set():
                return
            # All other accounts are peers
            peers = [a for a in accounts if a.id != account.id]
            result = await warmup_single_account(account, peers, db, cancel_event)
            totals["total_sent"] += result["sent"]
            totals["total_received"] += result["received"]
            totals["total_errors"] += result["errors"]
            totals["accounts_processed"] += 1
            engine_manager.increment_completed(EngineType.WARMUP)

    tasks = [process_one(acc) for acc in accounts if acc.status != AccountStatus.WARMED]
    await asyncio.gather(*tasks, return_exceptions=True)

    engine_manager.finish_engine(EngineType.WARMUP)
    logger.info(f"[OK] Warmup batch complete: {totals}")
    return totals
