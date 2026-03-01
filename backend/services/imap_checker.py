"""
IMAP Login Verification — checks that a freshly created account can actually login.
Runs as a quick post-birth check to separate "registered" from "verified working".
"""
import imaplib
import asyncio
from datetime import datetime
from loguru import logger


# IMAP server config per provider
IMAP_SERVERS = {
    "yahoo":   ("imap.mail.yahoo.com", 993),
    "aol":     ("imap.aol.com", 993),
    "gmail":   ("imap.gmail.com", 993),
    "outlook": ("imap-mail.outlook.com", 993),
    "hotmail": ("imap-mail.outlook.com", 993),
}


def imap_login_check(email: str, password: str, provider: str, timeout: int = 15) -> dict:
    """
    Synchronous IMAP login check.
    Returns: {"success": bool, "error": str|None, "inbox_count": int|None}
    """
    server_info = IMAP_SERVERS.get(provider.lower())
    if not server_info:
        return {"success": False, "error": f"Unknown provider: {provider}", "inbox_count": None}

    host, port = server_info
    try:
        imap = imaplib.IMAP4_SSL(host, port, timeout=timeout)
        try:
            status, data = imap.login(email, password)
            if status == "OK":
                # Quick inbox count
                inbox_count = None
                try:
                    imap.select("INBOX", readonly=True)
                    _, msg_data = imap.search(None, "ALL")
                    inbox_count = len(msg_data[0].split()) if msg_data[0] else 0
                except Exception:
                    pass
                imap.logout()
                logger.info(f"[IMAP] ✅ {email} — login OK (inbox: {inbox_count})")
                return {"success": True, "error": None, "inbox_count": inbox_count}
            else:
                imap.logout()
                return {"success": False, "error": f"Login failed: {status}", "inbox_count": None}
        except imaplib.IMAP4.error as e:
            error_msg = str(e)
            # Yahoo-specific: "LOGIN Web login required" means app password needed
            if "Web login" in error_msg or "LOGIN" in error_msg:
                logger.warning(f"[IMAP] ⚠️ {email} — {error_msg} (may need app password)")
            return {"success": False, "error": error_msg[:200], "inbox_count": None}
        finally:
            try:
                imap.logout()
            except Exception:
                pass
    except (TimeoutError, OSError, ConnectionRefusedError) as e:
        return {"success": False, "error": f"Connection error: {e}", "inbox_count": None}
    except Exception as e:
        return {"success": False, "error": str(e)[:200], "inbox_count": None}


async def imap_login_check_async(email: str, password: str, provider: str, timeout: int = 15) -> dict:
    """Async wrapper — runs IMAP check in a thread to avoid blocking the event loop."""
    return await asyncio.to_thread(imap_login_check, email, password, provider, timeout)


async def verify_account_imap(account, db, _log=None, _err=None) -> bool:
    """
    Full verification flow: IMAP login check + update account status in DB.
    Returns True if IMAP login succeeded.
    """
    log_fn = _log or (lambda msg: logger.info(f"[IMAP] {msg}"))
    err_fn = _err or (lambda msg: logger.error(f"[IMAP] {msg}"))

    log_fn(f"IMAP check: {account.email}...")

    # Wait a bit after birth — servers need time to propagate
    await asyncio.sleep(5)

    result = await imap_login_check_async(
        email=account.email,
        password=account.password,
        provider=account.provider,
    )

    if result["success"]:
        log_fn(f"✅ IMAP OK: {account.email} (inbox: {result['inbox_count']})")
        account.imap_verified = True
        account.imap_checked_at = datetime.utcnow()
        try:
            db.commit()
        except Exception:
            pass
        return True
    else:
        err_fn(f"⚠️ IMAP fail: {account.email} — {result['error']}")
        account.imap_verified = False
        account.imap_checked_at = datetime.utcnow()
        try:
            db.commit()
        except Exception:
            pass
        return False
