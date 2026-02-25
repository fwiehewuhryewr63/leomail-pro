"""
Leomail v4 — SMTP Sender
Direct SMTP connection for burn-model sending.
Each provider: host, port, TLS config.
"""
import smtplib
import ssl
import random
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from loguru import logger


# ─── Provider SMTP Settings ──────────────────────────────────────────────────

SMTP_SETTINGS = {
    "gmail": {"host": "smtp.gmail.com", "port": 587, "tls": True},
    "yahoo": {"host": "smtp.mail.yahoo.com", "port": 587, "tls": True},
    "aol":   {"host": "smtp.aol.com", "port": 587, "tls": True},
    "outlook": {"host": "smtp-mail.outlook.com", "port": 587, "tls": True},
    "hotmail": {"host": "smtp-mail.outlook.com", "port": 587, "tls": True},
}


# ─── Result Codes ─────────────────────────────────────────────────────────────

class SendResult:
    OK = "ok"
    RATE_LIMIT = "rate_limit"        # 421: temporary, retry after delay
    BOUNCE = "bounce"                # 550: permanent, recipient bad
    AUTH_FAIL = "auth_fail"          # 535/553: account dead
    SUSPENDED = "suspended"          # 550/account disabled
    NETWORK = "network"              # timeout/connection error
    UNKNOWN = "unknown"


def classify_smtp_error(code: int, message: str) -> str:
    """Classify SMTP error into actionable result."""
    msg_lower = message.lower()

    if code in (421, 450, 451):
        return SendResult.RATE_LIMIT
    if code in (535, 534):
        return SendResult.AUTH_FAIL
    if code == 550:
        if "suspended" in msg_lower or "disabled" in msg_lower or "blocked" in msg_lower:
            return SendResult.SUSPENDED
        return SendResult.BOUNCE
    if code in (552, 553, 554):
        if "auth" in msg_lower or "credential" in msg_lower:
            return SendResult.AUTH_FAIL
        return SendResult.SUSPENDED
    if code == 0:
        return SendResult.NETWORK

    return SendResult.UNKNOWN


# ─── SMTP Send ────────────────────────────────────────────────────────────────

def _build_message(
    from_email: str,
    from_name: str,
    to_email: str,
    subject: str,
    body_html: str,
) -> MIMEMultipart:
    """Build MIME email message."""
    msg = MIMEMultipart("alternative")
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["Date"] = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")
    # Random Message-ID for uniqueness
    rand_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=16))
    domain = from_email.split("@")[1] if "@" in from_email else "mail.com"
    msg["Message-ID"] = f"<{rand_id}@{domain}>"

    # Plain text fallback (strip HTML tags roughly)
    import re
    plain_text = re.sub(r'<[^>]+>', '', body_html)
    plain_text = re.sub(r'\s+', ' ', plain_text).strip()

    msg.attach(MIMEText(plain_text, "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    return msg


def send_email(
    account_email: str,
    account_password: str,
    provider: str,
    to_email: str,
    subject: str,
    body_html: str,
    from_name: str = "",
    timeout: int = 30,
) -> tuple[str, str]:
    """
    Send a single email via SMTP.
    
    Returns: (result_code, detail_message)
        result_code: SendResult.OK / RATE_LIMIT / BOUNCE / AUTH_FAIL / SUSPENDED / NETWORK
        detail_message: human-readable description
    """
    settings = SMTP_SETTINGS.get(provider)
    if not settings:
        return SendResult.UNKNOWN, f"Unknown provider: {provider}"

    if not from_name:
        from_name = account_email.split("@")[0].replace(".", " ").title()

    msg = _build_message(account_email, from_name, to_email, subject, body_html)

    try:
        if settings["tls"]:
            server = smtplib.SMTP(settings["host"], settings["port"], timeout=timeout)
            server.ehlo()
            context = ssl.create_default_context()
            server.starttls(context=context)
            server.ehlo()
        else:
            context = ssl.create_default_context()
            server = smtplib.SMTP_SSL(settings["host"], settings["port"],
                                       context=context, timeout=timeout)

        server.login(account_email, account_password)
        server.sendmail(account_email, to_email, msg.as_string())
        server.quit()

        return SendResult.OK, "Sent successfully"

    except smtplib.SMTPAuthenticationError as e:
        code = e.smtp_code if hasattr(e, 'smtp_code') else 535
        detail = str(e)
        result = classify_smtp_error(code, detail)
        logger.warning(f"SMTP auth error [{account_email}]: {code} {detail[:100]}")
        return result, detail[:200]

    except smtplib.SMTPRecipientsRefused as e:
        detail = str(e)
        logger.debug(f"SMTP recipient refused [{to_email}]: {detail[:100]}")
        return SendResult.BOUNCE, detail[:200]

    except smtplib.SMTPSenderRefused as e:
        code = e.smtp_code if hasattr(e, 'smtp_code') else 550
        detail = str(e)
        result = classify_smtp_error(code, detail)
        logger.warning(f"SMTP sender refused [{account_email}]: {code} {detail[:100]}")
        return result, detail[:200]

    except smtplib.SMTPDataError as e:
        code = e.smtp_code if hasattr(e, 'smtp_code') else 550
        detail = str(e)
        result = classify_smtp_error(code, detail)
        logger.warning(f"SMTP data error [{account_email}]: {code} {detail[:100]}")
        return result, detail[:200]

    except smtplib.SMTPServerDisconnected:
        logger.warning(f"SMTP disconnected [{account_email}]")
        return SendResult.NETWORK, "Server disconnected"

    except (TimeoutError, ConnectionError, OSError) as e:
        logger.warning(f"SMTP network error [{account_email}]: {e}")
        return SendResult.NETWORK, str(e)[:200]

    except Exception as e:
        logger.error(f"SMTP unexpected error [{account_email}]: {e}")
        return SendResult.UNKNOWN, str(e)[:200]


# ─── Gmail App Password Note ─────────────────────────────────────────────────
# Gmail requires an "App Password" for SMTP access (not the account password).
# For burn accounts, we'll need to either:
# 1. Enable "Less Secure Apps" during birth (deprecated by Google)
# 2. Generate App Password during birth via browser automation
# 3. Use IMAP OAuth (more complex)
# For Yahoo/AOL/Outlook, regular password works with SMTP.
