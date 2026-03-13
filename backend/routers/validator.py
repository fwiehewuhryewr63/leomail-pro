"""
Validator Router — File upload, account parsing, validation engine control.

Endpoints:
    POST /api/validator/upload    — Upload accounts file (multipart)
    POST /api/validator/start     — Start validation
    POST /api/validator/stop      — Stop validation
    GET  /api/validator/status    — Get validation progress
    GET  /api/validator/results   — Get validation results
"""
import os
import re
import asyncio
import threading
import random
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from loguru import logger

from ..database import SessionLocal, PROJECT_ROOT
from ..models import Account, AccountStatus, Task, TaskStatus, ThreadLog, Proxy, Farm, farm_accounts
from ..services.proxy_manager import ProxyManager
from ..services.engine_manager import engine_manager, EngineType, EngineStatus

router = APIRouter(prefix="/api/validator", tags=["validator"])


class ProxyError(Exception):
    """Proxy connection failed — retryable. Distinct from invalid credentials."""
    pass


# Retry config for proxy hiccups (residential/mobile proxies recover in 30s-2min)
MAX_PROXY_RETRIES = 3
RETRY_DELAYS = [30, 60, 90]  # seconds between retries

# ─── State ──────────────────────────────────────────────────────────────────
VALIDATOR_CANCEL_EVENT = threading.Event()
_state_lock = threading.Lock()  # protects _validator_state counters from race conditions
_validator_state = {
    "running": False,
    "parsed_accounts": [],          # [{email, password, recovery, provider}]
    "filename": None,
    "format": None,
    "total": 0,
    "valid": 0,
    "invalid": 0,
    "challenge": 0,                 # accounts that hit challenges (2FA, device verify, CAPTCHA)
    "skipped": 0,                   # accounts skipped (e.g. Gmail without proxy)
    "processing": 0,
    "threads": 1,
    "thread_logs": [],              # per-thread status
    "results": [],                  # [{email, provider, status, time_sec, error}]
    "task_id": None,
    "farm_id": None,
}

UPLOADS_DIR = PROJECT_ROOT / "user_data" / "validator"


def _reset_validator_runtime_state(*, clear_loaded: bool = False):
    """Recover validator state after a failed or stale start without nuking uploaded input by default."""
    _validator_state["running"] = False
    _validator_state["valid"] = 0
    _validator_state["invalid"] = 0
    _validator_state["challenge"] = 0
    _validator_state["skipped"] = 0
    _validator_state["processing"] = 0
    _validator_state["thread_logs"] = []
    _validator_state["results"] = []
    _validator_state["task_id"] = None
    _validator_state["farm_id"] = None
    if clear_loaded:
        _validator_state["parsed_accounts"] = []
        _validator_state["filename"] = None
        _validator_state["format"] = None
        _validator_state["total"] = 0


# ─── Provider Detection ─────────────────────────────────────────────────────
PROVIDER_MAP = {
    "gmail.com": "gmail",
    "googlemail.com": "gmail",
    "yahoo.com": "yahoo",
    "ymail.com": "yahoo",
    "aol.com": "aol",
    "outlook.com": "outlook",
    "hotmail.com": "hotmail",
    "live.com": "hotmail",
    "msn.com": "hotmail",
    "protonmail.com": "protonmail",
    "proton.me": "protonmail",
    "pm.me": "protonmail",
    "web.de": "webde",
}


def detect_provider(email: str) -> str | None:
    """Auto-detect provider from email domain."""
    domain = email.split("@")[-1].lower().strip()
    return PROVIDER_MAP.get(domain)


# ─── File Parsing ────────────────────────────────────────────────────────────
def parse_accounts_file(content: str) -> tuple[list[dict], str]:
    """
    Parse accounts from file content.
    Supported formats:
        email:password
        email:password:recovery
        email;password
        email;password;recovery
        email|password
        email|password|recovery
        email password
        email\tpassword
    Returns (accounts_list, detected_format)
    """
    def normalize_optional_recovery(value: str | None) -> str | None:
        if not value:
            return None
        candidate = value.strip().strip('"').strip("'")
        # Ignore trailing metadata like webhooks or notes; only keep plausible recovery emails.
        if "@" in candidate and "." in candidate:
            return candidate
        return None

    accounts = []
    fmt = "unknown"
    # Strip BOM (Byte Order Mark) — UTF-8 BOM files have invisible \ufeff prefix
    content = content.lstrip("\ufeff")
    lines = content.strip().splitlines()

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Try different separators
        parts = None
        if ";" in line:
            parts = line.split(";", 3)
            fmt = "semicolon"
        elif "|" in line:
            parts = line.split("|", 3)
            fmt = "pipe"
        elif "\t" in line:
            parts = line.split("\t", 3)
            fmt = "tab"
        elif ":" in line:
            parts = line.split(":", 3)
            fmt = "colon"
        elif re.search(r"\s+", line):
            parts = re.split(r"\s+", line, maxsplit=3)
            fmt = "space"

        if not parts or len(parts) < 2:
            continue

        email = parts[0].strip().strip('"').strip("'")
        password = parts[1].strip().strip('"').strip("'")
        recovery = normalize_optional_recovery(parts[2]) if len(parts) > 2 else None

        # Basic email validation
        if "@" not in email or "." not in email:
            continue

        provider = detect_provider(email)
        if not provider:
            continue  # unsupported provider

        accounts.append({
            "email": email,
            "password": password,
            "recovery": recovery,
            "provider": provider,
        })

    # Determine format string
    has_recovery = any(a["recovery"] for a in accounts)
    if fmt == "colon":
        fmt_str = "email:password:recovery" if has_recovery else "email:password"
    elif fmt == "semicolon":
        fmt_str = "email;password;recovery" if has_recovery else "email;password"
    elif fmt == "pipe":
        fmt_str = "email|password|recovery" if has_recovery else "email|password"
    else:
        fmt_str = f"email{fmt}password"

    return accounts, fmt_str


# ─── Upload Endpoint ────────────────────────────────────────────────────────
@router.post("/upload")
async def upload_accounts_file(file: UploadFile = File(...)):
    """Upload and parse an accounts file."""
    if _validator_state["running"]:
        raise HTTPException(400, "Validator is running. Stop it first.")

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    # Read file
    try:
        raw = await file.read()
        # Try UTF-8, fallback to latin-1
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            content = raw.decode("latin-1")
    except Exception as e:
        raise HTTPException(400, f"Failed to read file: {e}")

    # Parse
    accounts, fmt = parse_accounts_file(content)
    if not accounts:
        raise HTTPException(
            400,
            "No valid accounts found in file. Supported: email:password, email;password, "
            "email|password, email password, email<TAB>password, optional recovery as the third field, "
            "and extra trailing fields are ignored",
        )

    # Detect providers
    providers = set(a["provider"] for a in accounts)
    provider_counts = {}
    for a in accounts:
        p = a["provider"]
        provider_counts[p] = provider_counts.get(p, 0) + 1

    # Save file for reference
    save_path = UPLOADS_DIR / file.filename
    with open(save_path, "wb") as f:
        f.write(raw)

    # Update state
    _validator_state["parsed_accounts"] = accounts
    _validator_state["filename"] = file.filename
    _validator_state["format"] = fmt
    _validator_state["total"] = len(accounts)
    _validator_state["valid"] = 0
    _validator_state["invalid"] = 0
    _validator_state["processing"] = 0
    _validator_state["results"] = []
    _validator_state["thread_logs"] = []

    return {
        "status": "ok",
        "filename": file.filename,
        "total": len(accounts),
        "format": fmt,
        "providers": provider_counts,
        "has_recovery": any(a["recovery"] for a in accounts),
    }


# ─── Start Validation ───────────────────────────────────────────────────────
class ValidatorStartRequest(BaseModel):
    threads: int = 5
    skip_existing: bool = True
    save_session: bool = True
    farm_name: str = ""     # auto-generated if empty


@router.post("/start")
async def start_validation(request: ValidatorStartRequest):
    """Start account validation."""
    engine = engine_manager.get_engine(EngineType.VALIDATOR)
    if _validator_state["running"] and engine.status == EngineStatus.IDLE and _validator_state["processing"] == 0:
        logger.warning("[Validator] Detected stale running state with idle engine; recovering state before restart")
        _reset_validator_runtime_state()

    if _validator_state["running"]:
        raise HTTPException(400, "Validator is already running")
    if not _validator_state["parsed_accounts"]:
        raise HTTPException(400, "No accounts loaded. Upload a file first.")

    VALIDATOR_CANCEL_EVENT.clear()
    _validator_state["running"] = True
    _validator_state["valid"] = 0
    _validator_state["invalid"] = 0
    _validator_state["challenge"] = 0
    _validator_state["skipped"] = 0
    _validator_state["processing"] = 0
    _validator_state["threads"] = request.threads
    _validator_state["results"] = []
    _validator_state["thread_logs"] = []

    db = SessionLocal()
    task_id = None
    farm_id = None

    try:
        # Skip existing accounts
        accounts_to_validate = list(_validator_state["parsed_accounts"])
        if request.skip_existing:
            existing_emails = set(
                row[0] for row in db.query(Account.email).all()
            )
            before = len(accounts_to_validate)
            accounts_to_validate = [a for a in accounts_to_validate if a["email"] not in existing_emails]
            skipped = before - len(accounts_to_validate)
            if skipped > 0:
                logger.info(f"[Validator] Skipped {skipped} existing accounts")
                _validator_state["total"] = len(accounts_to_validate)

        if not accounts_to_validate:
            _validator_state["running"] = False
            return {"status": "error", "message": "All accounts already exist in database"}

        # Create task record
        task = Task(
            type="validator",
            status=TaskStatus.RUNNING,
            total_items=len(accounts_to_validate),
            thread_count=request.threads,
            details=f"Validating {len(accounts_to_validate)} accounts from {_validator_state['filename']}",
        )
        db.add(task)
        db.commit()
        task_id = task.id
        _validator_state["task_id"] = task_id

        # Create farm
        if request.farm_name:
            farm_name = request.farm_name
        else:
            date_str = datetime.now().strftime('%Y.%m.%d')
            providers = set(a["provider"] for a in accounts_to_validate)
            provider_label = "+".join(sorted(p.capitalize() for p in providers))
            farm_name = f"Import / {provider_label} / {date_str}"

        farm = Farm(name=farm_name)
        db.add(farm)
        db.commit()
        farm_id = farm.id
        _validator_state["farm_id"] = farm_id
        logger.info(f"[Validator] Created farm: {farm_name} (ID: {farm_id})")

        # Integrate with EngineManager
        engine_manager.start_engine(EngineType.VALIDATOR, request.threads, len(accounts_to_validate), task_id)

        # Launch validation in a dedicated daemon thread.
        # In the boxed/VPS runtime this is more predictable than relying on
        # the request loop's default executor for a long-lived threaded worker pool.
        launch_thread = threading.Thread(
            target=_run_validator_pool,
            args=(
                accounts_to_validate,
                request.threads,
                request.save_session,
                task_id,
                farm_id,
            ),
            daemon=True,
            name=f"ValidatorPool-{task_id}",
        )
        launch_thread.start()
        logger.info(f"[Validator] Background pool launched (task={task_id}, farm={farm_id})")

        return {
            "status": "ok",
            "message": f"Validation started: {len(accounts_to_validate)} accounts, {request.threads} threads",
            "total": len(accounts_to_validate),
            "farm_name": farm_name,
        }
    except Exception as e:
        logger.exception(f"[Validator] Failed to start validation: {e}")
        _reset_validator_runtime_state()

        if engine_manager.get_engine(EngineType.VALIDATOR).status != EngineStatus.IDLE:
            engine_manager.finish_engine(EngineType.VALIDATOR)

        db.rollback()
        try:
            if task_id:
                task = db.query(Task).get(task_id)
                if task:
                    task.status = TaskStatus.FAILED
                    task.stop_reason = f"Failed to start validator: {str(e)[:200]}"
                    task.completed_at = datetime.utcnow()
            if farm_id:
                farm = db.query(Farm).get(farm_id)
                if farm:
                    db.delete(farm)
            db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(500, f"Failed to start validation: {str(e)[:160]}")
    finally:
        db.close()


# ─── Stop Validation ────────────────────────────────────────────────────────
@router.post("/stop")
async def stop_validation():
    """Stop validation process."""
    if not _validator_state["running"]:
        return {"status": "ok", "message": "Not running"}

    VALIDATOR_CANCEL_EVENT.set()
    _validator_state["running"] = False
    engine_manager.stop_engine(EngineType.VALIDATOR)

    # Update task
    db = SessionLocal()
    if _validator_state["task_id"]:
        task = db.query(Task).get(_validator_state["task_id"])
        if task:
            task.status = TaskStatus.STOPPED
            task.stop_reason = "Stopped by user"
            task.completed_at = datetime.utcnow()
            db.commit()
    db.close()

    return {"status": "ok", "message": "Validation stopped"}


# ─── Status ─────────────────────────────────────────────────────────────────
@router.get("/status")
async def get_status():
    """Get validation progress."""
    engine = engine_manager.get_engine(EngineType.VALIDATOR)
    if _validator_state["running"] and engine.status == EngineStatus.IDLE and _validator_state["processing"] == 0:
        logger.warning("[Validator] Status endpoint detected stale running state; recovering runtime flags")
        _reset_validator_runtime_state()

    return {
        "running": _validator_state["running"],
        "filename": _validator_state["filename"],
        "format": _validator_state["format"],
        "total": _validator_state["total"],
        "valid": _validator_state["valid"],
        "invalid": _validator_state["invalid"],
        "challenge": _validator_state["challenge"],
        "skipped": _validator_state["skipped"],
        "processing": _validator_state["processing"],
        "threads": _validator_state["threads"],
        "thread_logs": _validator_state["thread_logs"],
    }


# ─── Results ────────────────────────────────────────────────────────────────
@router.get("/results")
async def get_results():
    """Get validation results."""
    return {
        "results": _validator_state["results"],
        "total": _validator_state["total"],
        "valid": _validator_state["valid"],
        "invalid": _validator_state["invalid"],
        "challenge": _validator_state["challenge"],
        "skipped": _validator_state["skipped"],
    }


# ─── Provider Login Configs ─────────────────────────────────────────────────
# Each provider defines: login URL, selectors, inbox URL, error patterns
PROVIDER_LOGIN_CONFIG = {
    "gmail": {
        "login_url": "https://accounts.google.com/signin/v2/identifier",
        "email_selectors": ['input[type="email"]', '#identifierId', 'input[name="identifier"]'],
        "email_next": ['#identifierNext button', '#identifierNext'],
        "password_selectors": ['input[type="password"]', 'input[name="Passwd"]', 'input[name="password"]'],
        "password_next": ['#passwordNext button', '#passwordNext'],
        "inbox_url": "https://mail.google.com/mail/u/0/#inbox",
        "inbox_indicators": ["mail.google.com", "myaccount.google.com"],
        "fail_indicators": ["accounts.google.com/signin"],  # Removed /v3/ — it's a UI version, not a failure
        "not_found": ["couldn't find", "couldn't find your google", "account not found"],
        "wrong_password": ["wrong password", "incorrect password", "password is incorrect"],
        "recovery_selectors": ['input#knowledge-preregistered-email-response',
                               'input[name="knowledgeLoginHint"]', 'input[aria-label*="email"]'],
    },
    "yahoo": {
        "login_url": "https://login.yahoo.com/",
        "email_selectors": ['input[name="username"]', '#login-username', 'input[type="text"]'],
        "email_next": ['button[name="signin"]', '#login-signin', 'button[type="submit"]'],
        "password_selectors": ['input[name="password"]', '#login-passwd', 'input[type="password"]'],
        "password_next": ['button[name="verifyPassword"]', '#login-signin', 'button[type="submit"]'],
        "inbox_url": "https://mail.yahoo.com/d/folders/1",
        "inbox_indicators": ["mail.yahoo.com"],
        "fail_indicators": ["login.yahoo.com"],
        "not_found": ["sorry, we don't recognize", "that username isn't right"],
        "wrong_password": ["invalid password", "wrong password"],
        "recovery_selectors": [],
    },
    "aol": {
        "login_url": "https://login.aol.com/",
        "email_selectors": ['input[name="username"]', '#login-username', 'input[type="text"]'],
        "email_next": ['button[name="signin"]', '#login-signin', 'button[type="submit"]'],
        "password_selectors": ['input[name="password"]', '#login-passwd', 'input[type="password"]'],
        "password_next": ['button[name="verifyPassword"]', '#login-signin', 'button[type="submit"]'],
        "inbox_url": "https://mail.aol.com/d/folders/1",
        "inbox_indicators": ["mail.aol.com"],
        "fail_indicators": ["login.aol.com"],
        "not_found": ["sorry, we don't recognize", "that username isn't right"],
        "wrong_password": ["invalid password", "wrong password"],
        "recovery_selectors": [],
    },
    "outlook": {
        "login_url": "https://login.live.com/",
        "email_selectors": ['input[type="email"]', 'input[name="loginfmt"]'],
        "email_next": ['input[type="submit"]', '#idSIButton9'],
        "password_selectors": ['input[type="password"]', 'input[name="passwd"]'],
        "password_next": ['input[type="submit"]', '#idSIButton9'],
        "inbox_url": "https://outlook.live.com/mail/0/inbox",
        "inbox_indicators": ["outlook.live.com/mail", "outlook.office.com"],
        "fail_indicators": ["login.live.com", "signup.live.com"],
        "not_found": ["that microsoft account doesn't exist", "no account found"],
        "wrong_password": ["your account or password is incorrect", "password is incorrect"],
        "recovery_selectors": [],
    },
    "hotmail": {  # Same as outlook
        "login_url": "https://login.live.com/",
        "email_selectors": ['input[type="email"]', 'input[name="loginfmt"]'],
        "email_next": ['input[type="submit"]', '#idSIButton9'],
        "password_selectors": ['input[type="password"]', 'input[name="passwd"]'],
        "password_next": ['input[type="submit"]', '#idSIButton9'],
        "inbox_url": "https://outlook.live.com/mail/0/inbox",
        "inbox_indicators": ["outlook.live.com/mail", "outlook.office.com"],
        "fail_indicators": ["login.live.com", "signup.live.com"],
        "not_found": ["that microsoft account doesn't exist", "no account found"],
        "wrong_password": ["your account or password is incorrect", "password is incorrect"],
        "recovery_selectors": [],
    },
    "protonmail": {
        "login_url": "https://account.proton.me/login",
        "email_selectors": ['input[id="username"]', 'input[name="username"]', 'input[placeholder*="email"]'],
        "email_next": [],  # Proton has email+password on same page
        "password_selectors": ['input[id="password"]', 'input[name="password"]', 'input[type="password"]'],
        "password_next": ['button[type="submit"]', 'button:has-text("Sign in")'],
        "inbox_url": "https://mail.proton.me/u/0/inbox",
        "inbox_indicators": ["mail.proton.me"],
        "fail_indicators": ["account.proton.me/login"],
        "not_found": [],
        "wrong_password": ["incorrect login credentials", "wrong credentials"],
        "recovery_selectors": [],
    },
    "webde": {
        "login_url": "https://web.de/",
        "email_selectors": ['input[name="username"]', '#freemailLoginUsername', 'input[id="freemailLoginUsername"]'],
        "email_next": [],  # Web.de has email+password on same page
        "password_selectors": ['input[name="password"]', '#freemailLoginPassword', 'input[id="freemailLoginPassword"]'],
        "password_next": ['button[type="submit"]', 'button:has-text("Login")', '#login', 'button:has-text("Anmelden")'],
        "inbox_url": "https://3c.web.de/mail/client",
        "inbox_indicators": ["web.de/mail", "3c.web.de"],
        "fail_indicators": ["web.de/registration"],
        "not_found": [],
        "wrong_password": ["falsches passwort", "incorrect password", "login fehlgeschlagen"],
        "recovery_selectors": [],
    },
}


# ─── Validation Worker Pool ─────────────────────────────────────────────────
def _run_validator_pool(accounts: list, threads: int, save_session_flag: bool, task_id: int, farm_id: int):
    """
    Run validation in a thread pool.
    ALL providers use browser login — no IMAP.
    Each thread gets its own BrowserManager + proxy.
    """
    import queue
    import time

    q = queue.Queue()
    for acc in accounts:
        q.put(acc)

    # Get proxies for browser validation
    proxy_list = []
    try:
        db_proxy = SessionLocal()
        pm = ProxyManager(db_proxy)
        proxy_list = pm.get_proxy_pool(threads)
        db_proxy.close()
        if proxy_list:
            logger.info(f"[Validator] Got {len(proxy_list)} proxies for browser validation")
        else:
            logger.warning("[Validator] No proxies available — running without proxy")
    except Exception as e:
        logger.warning(f"[Validator] Proxy pool error: {e} — running without proxies")

    # Initialize thread logs
    _validator_state["thread_logs"] = [
        {"index": i, "status": "idle", "email": None, "current_step": None, "error": None}
        for i in range(threads)
    ]

    def worker(thread_idx: int):
        """Single validation thread — browser-only."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        db = SessionLocal()
        browser_manager = None

        # Assign proxy to this thread
        proxy = proxy_list[thread_idx] if thread_idx < len(proxy_list) else None

        try:
            while not VALIDATOR_CANCEL_EVENT.is_set():
                try:
                    acc = q.get_nowait()
                except queue.Empty:
                    break

                email = acc["email"]
                password = acc["password"]
                recovery = acc.get("recovery")
                provider = acc["provider"]

                # ── Gmail-without-proxy guard ──
                if provider == "gmail" and not proxy:
                    logger.warning(f"[Validator] T-{thread_idx+1} {email}: Gmail requires proxy — skipped")
                    with _state_lock:
                        _validator_state["skipped"] += 1
                        _validator_state["results"].append({
                            "email": email, "provider": provider,
                            "status": "skipped", "time_sec": 0,
                            "error": "Gmail requires proxy",
                        })
                    _validator_state["thread_logs"][thread_idx] = {
                        "index": thread_idx, "status": "skipped",
                        "email": email, "current_step": "⚠ Gmail requires proxy — skipped",
                        "error": "Gmail requires proxy",
                    }
                    continue

                # Update thread log
                _validator_state["thread_logs"][thread_idx] = {
                    "index": thread_idx,
                    "status": "running",
                    "email": email,
                    "current_step": f"Validating {provider}...",
                    "error": None,
                }
                with _state_lock:
                    _validator_state["processing"] += 1

                start_time = time.time()
                validation_result = False  # True, False, or string status ("challenge")
                error_msg = None

                try:
                    # Start browser if not running
                    if not browser_manager:
                        _validator_state["thread_logs"][thread_idx]["current_step"] = "Starting browser engine..."
                        from ..modules.browser_manager import BrowserManager
                        browser_manager = BrowserManager(headless=False)
                        loop.run_until_complete(browser_manager.start())
                        logger.info(f"[Validator] T-{thread_idx+1} Browser engine started")

                    # ── Retry loop for proxy hiccups ──
                    for attempt in range(MAX_PROXY_RETRIES + 1):
                        try:
                            validation_result = loop.run_until_complete(
                                _validate_browser(
                                    email, password, recovery, provider, thread_idx,
                                    save_session_flag, db, browser_manager, proxy, farm_id
                                )
                            )
                            break  # Success or definitive invalid — exit retry loop
                        except ProxyError as pe:
                            if attempt < MAX_PROXY_RETRIES:
                                delay = RETRY_DELAYS[attempt]
                                logger.warning(
                                    f"[Validator] T-{thread_idx+1} Proxy hiccup for {email}: {pe} — "
                                    f"retry {attempt+1}/{MAX_PROXY_RETRIES} in {delay}s..."
                                )
                                _validator_state["thread_logs"][thread_idx]["current_step"] = (
                                    f"⚠ Proxy hiccup, retry in {delay}s ({attempt+1}/{MAX_PROXY_RETRIES})..."
                                )
                                # Wait for proxy to recover (check cancel every 1s for responsiveness)
                                cancelled = False
                                for _sec in range(delay):
                                    if VALIDATOR_CANCEL_EVENT.is_set():
                                        cancelled = True
                                        break
                                    time.sleep(1)
                                if cancelled:
                                    break
                                # Recreate browser context (old context is dead after proxy fail)
                                try:
                                    loop.run_until_complete(browser_manager.stop())
                                except Exception:
                                    pass
                                browser_manager = BrowserManager(headless=False)
                                loop.run_until_complete(browser_manager.start())
                                logger.info(f"[Validator] T-{thread_idx+1} Browser restarted for retry")
                            else:
                                error_msg = f"Proxy failed after {MAX_PROXY_RETRIES} retries: {pe}"
                                logger.error(f"[Validator] T-{thread_idx+1} {error_msg}")
                except Exception as e:
                    error_msg = str(e)[:200]
                    logger.error(f"[Validator] T-{thread_idx+1} Error validating {email}: {e}")

                elapsed = round(time.time() - start_time, 1)
                with _state_lock:
                    _validator_state["processing"] -= 1

                # ── Classify result ──
                if validation_result is True:
                    status = "valid"
                    with _state_lock:
                        _validator_state["valid"] += 1
                elif validation_result == "challenge":
                    status = "challenge"
                    with _state_lock:
                        _validator_state["challenge"] += 1
                else:
                    status = "invalid"
                    with _state_lock:
                        _validator_state["invalid"] += 1

                # ── Determine display text ──
                if status == "valid":
                    step_text = "Valid ✓"
                    log_status = "completed"
                elif status == "challenge":
                    step_text = error_msg or "⚠ Challenge / verification required"
                    log_status = "challenge"
                else:
                    step_text = error_msg or "Invalid credentials"
                    log_status = "error"

                # Record result
                with _state_lock:
                    _validator_state["results"].append({
                        "email": email,
                        "provider": provider,
                        "status": status,
                        "time_sec": elapsed,
                        "error": error_msg,
                    })

                # Update thread log
                _validator_state["thread_logs"][thread_idx] = {
                    "index": thread_idx,
                    "status": log_status,
                    "email": email,
                    "current_step": step_text,
                    "error": error_msg,
                }

                # Update task progress
                try:
                    task = db.query(Task).get(task_id)
                    if task:
                        task.completed_items = _validator_state["valid"] + _validator_state["invalid"] + _validator_state["challenge"] + _validator_state["skipped"]
                        db.commit()
                except Exception:
                    db.rollback()

        except Exception:
            logger.exception(f"[Validator] Worker {thread_idx} crashed")
        finally:
            if browser_manager:
                try:
                    loop.run_until_complete(browser_manager.stop())
                except Exception:
                    pass
            db.close()
            loop.close()

    logger.info(f"[Validator] Worker pool bootstrapping: {len(accounts)} accounts, {threads} threads")

    # Launch worker threads
    worker_threads = []
    for i in range(min(threads, len(accounts))):
        t = threading.Thread(target=worker, args=(i,), daemon=True)
        t.start()
        worker_threads.append(t)

    for t in worker_threads:
        t.join()

    # Finalize
    _validator_state["running"] = False
    _validator_state["processing"] = 0

    db = SessionLocal()
    try:
        task = db.query(Task).get(task_id)
        if task and task.status == TaskStatus.RUNNING:
            task.status = TaskStatus.COMPLETED
            task.completed_items = _validator_state["valid"] + _validator_state["invalid"] + _validator_state["challenge"] + _validator_state["skipped"]
            task.completed_at = datetime.utcnow()
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

    logger.info(
        f"[Validator] Done: {_validator_state['valid']} valid, "
        f"{_validator_state['invalid']} invalid, "
        f"{_validator_state['challenge']} challenge, "
        f"{_validator_state['skipped']} skipped out of {len(accounts)}"
    )
    engine_manager.finish_engine(EngineType.VALIDATOR)


# ─── Universal Browser Validation ──────────────────────────────────────────
async def _validate_browser(
    email: str, password: str, recovery: str | None, provider: str,
    thread_idx: int, save_session_flag: bool, db, browser_manager, proxy, farm_id: int
) -> bool:
    """
    Validate ANY provider account via browser login.
    Uses PROVIDER_LOGIN_CONFIG for per-provider selectors and URLs.
    Flow: login page → email → password → handle challenges → verify inbox.
    On success: saves session, fingerprint, creates Account in DB, adds to farm.
    """
    from ..modules.screenshot import debug_screenshot

    config = PROVIDER_LOGIN_CONFIG.get(provider)
    if not config:
        logger.warning(f"[Validator] T-{thread_idx+1} No browser config for provider: {provider}")
        return False

    context = None
    page = None
    safe_email = email.split("@")[0][:20]
    _tlog = _validator_state["thread_logs"][thread_idx]

    try:
        # ── Create anti-detect browser context ──
        _tlog["current_step"] = "Creating browser context..."
        context = await browser_manager.create_context(proxy=proxy)
        page = await context.new_page()

        # ── Navigate to login page ──
        _tlog["current_step"] = f"Opening {provider} login..."
        try:
            await page.goto(config["login_url"], wait_until="domcontentloaded", timeout=30000)
        except Exception as nav_err:
            err_str = str(nav_err).lower()
            if any(x in err_str for x in ["timeout", "err_proxy", "err_tunnel",
                                           "err_connection", "connection_closed",
                                           "connection_refused", "net::err"]):
                raise ProxyError(f"Navigation failed: {nav_err}")
            raise  # Re-raise non-proxy errors as-is
        await asyncio.sleep(random.uniform(2, 4))

        # ── Check for proxy failure (chrome-error page) ──
        current_url = page.url or ""
        if "chrome-error" in current_url or current_url == "about:blank":
            raise ProxyError(f"Proxy navigation failed — got {current_url}")

        # ── Dismiss cookie consent banners (Yahoo, AOL, Web.de, Proton) ──
        for cookie_sel in [
            'button:has-text("Accept all")', 'button:has-text("Alle akzeptieren")',
            'button:has-text("Accept All")', 'button:has-text("Agree")',
            'button:has-text("Tout accepter")', 'button:has-text("Aceptar todo")',
            'button[name="agree"]', 'button.accept-all',
            '#consent-page button.accept-all',
            'button:has-text("I agree")', 'button:has-text("OK")',
            'button:has-text("Einwilligen")', 'button:has-text("Zustimmen")',
        ]:
            try:
                el = page.locator(cookie_sel)
                if await el.count() > 0 and await el.is_visible():
                    await el.click()
                    await asyncio.sleep(random.uniform(1, 2))
                    break
            except Exception:
                continue

        await debug_screenshot(page, f"val_{provider}_login_{safe_email}")

        # ── Enter email ──
        _tlog["current_step"] = f"Entering email: {email[:25]}..."
        email_input = await _find_element(page, config["email_selectors"])

        if not email_input:
            await debug_screenshot(page, f"val_{provider}_no_email_{safe_email}")
            logger.warning(f"[Validator] T-{thread_idx+1} No email field on {provider} for {email}")
            await context.close()
            return False

        await email_input.click()
        await asyncio.sleep(random.uniform(0.3, 0.7))
        await email_input.fill("")
        await email_input.type(email, delay=random.randint(30, 80))
        await asyncio.sleep(random.uniform(1, 2))

        # ── Click Next (email) — skip for providers with combined form ──
        if config["email_next"]:
            await _click_any(page, config["email_next"])
            await asyncio.sleep(random.uniform(3, 5))
            await debug_screenshot(page, f"val_{provider}_after_email_{safe_email}")

            # Check: account not found?
            body_text = await _get_page_text(page)
            if any(nf in body_text for nf in config.get("not_found", [])):
                _tlog["current_step"] = "Account not found"
                logger.info(f"[Validator] T-{thread_idx+1} {email}: account not found on {provider}")
                await context.close()
                return False

        # ── Enter password ──
        _tlog["current_step"] = "Entering password..."
        pwd_input = None
        for attempt in range(3):
            pwd_input = await _find_element(page, config["password_selectors"])
            if pwd_input:
                break
            await asyncio.sleep(2)

        if not pwd_input:
            await debug_screenshot(page, f"val_{provider}_no_pwd_{safe_email}")
            current_url = page.url.lower()
            if "challenge" in current_url or "rejected" in current_url or "blocked" in current_url:
                _tlog["current_step"] = f"Blocked by {provider}"
                logger.warning(f"[Validator] T-{thread_idx+1} {email}: blocked/challenged by {provider}")
                await context.close()
                return "challenge"  # Don't mark invalid — account may be alive
            else:
                _tlog["current_step"] = "No password field found"
            logger.warning(f"[Validator] T-{thread_idx+1} {email}: no password field on {provider}")
            await context.close()
            return False

        await pwd_input.click()
        await asyncio.sleep(random.uniform(0.3, 0.7))
        await pwd_input.fill("")
        await pwd_input.type(password, delay=random.randint(30, 80))
        await asyncio.sleep(random.uniform(1, 2))

        # ── Click Next (password) ──
        await _click_any(page, config["password_next"])
        await asyncio.sleep(random.uniform(4, 7))
        await debug_screenshot(page, f"val_{provider}_after_pwd_{safe_email}")

        # ── Check: wrong password? ──
        body_text = await _get_page_text(page)
        if any(wp in body_text for wp in config.get("wrong_password", [])):
            _tlog["current_step"] = "Wrong password"
            logger.info(f"[Validator] T-{thread_idx+1} {email}: wrong password on {provider}")
            await context.close()
            return False

        # ── Handle challenges ──
        current_url = page.url.lower()
        _tlog["current_step"] = "Handling challenges..."

        # Wait for redirect
        for _ in range(3):
            current_url = page.url.lower()
            # Check if already on inbox or account page
            if any(ind in current_url for ind in config["inbox_indicators"]):
                break
            if not any(fi in current_url for fi in config["fail_indicators"]):
                break
            await asyncio.sleep(2)

        # Try recovery email if challenge detected
        if "challenge" in current_url or "verify" in current_url:
            await debug_screenshot(page, f"val_{provider}_challenge_{safe_email}")
            if recovery and config.get("recovery_selectors"):
                _tlog["current_step"] = f"Entering recovery: {recovery[:15]}..."
                recovery_input = await _find_element(page, config["recovery_selectors"])
                if recovery_input:
                    await recovery_input.click()
                    await asyncio.sleep(0.5)
                    await recovery_input.fill("")
                    await recovery_input.type(recovery, delay=random.randint(30, 70))
                    await asyncio.sleep(1)
                    await _click_any(page, ['button:has-text("Next")', 'button:has-text("Далее")',
                                            'button:has-text("Weiter")', 'button[type="submit"]'])
                    await asyncio.sleep(random.uniform(4, 7))
                    await debug_screenshot(page, f"val_{provider}_after_recovery_{safe_email}")
                    # ── Post-recovery challenge re-check ──
                    # Google may show a SECOND verification step even after recovery email
                    post_recovery_url = page.url.lower()
                    if "challenge" in post_recovery_url or "verify" in post_recovery_url:
                        _tlog["current_step"] = "⚠ Challenge persists after recovery"
                        logger.info(f"[Validator] T-{thread_idx+1} {email}: challenge persists after recovery on {provider}")
                        await context.close()
                        return "challenge"
                else:
                    # Recovery selectors didn't match — challenge we can't handle
                    _tlog["current_step"] = "⚠ Challenge — recovery input not found"
                    logger.info(f"[Validator] T-{thread_idx+1} {email}: challenge, recovery input not found")
                    await context.close()
                    return "challenge"
            else:
                # No recovery email or no recovery selectors — can't handle challenge
                detail = "no recovery email" if not recovery else "no recovery selectors"
                _tlog["current_step"] = f"⚠ Challenge — {detail}"
                logger.info(f"[Validator] T-{thread_idx+1} {email}: challenge on {provider}, {detail}")
                await context.close()
                return "challenge"

        # ── Skip non-critical prompts (2FA, passkey, app promo, "Stay signed in?", etc.) ──
        for _ in range(5):
            skip_clicked = False
            # Button text matches (case-insensitive via has-text)
            skip_phrases = [
                # Generic
                "not now", "skip", "do this later", "remind me later",
                "no thanks", "maybe later", "i'll do it later", "cancel",
                # Microsoft: passkey/authenticator prompts
                "skip for now", "i want to use a different method",
                "use a different method", "use password instead",
                "other way to sign in", "try another way",
                # Russian
                "не сейчас", "пропустить",
                # German
                "später", "jetzt nicht", "überspringen",
                # Spanish
                "ahora no", "omitir",
                # French
                "pas maintenant", "ignorer",
            ]
            for phrase in skip_phrases:
                try:
                    skip_btn = page.locator(f'button:has-text("{phrase}")')
                    if await skip_btn.count() > 0 and await skip_btn.is_visible():
                        await skip_btn.click()
                        await asyncio.sleep(random.uniform(2, 4))
                        skip_clicked = True
                        break
                except Exception:
                    continue
            # Also try links and specific IDs
            if not skip_clicked:
                for sel in [
                    'a:has-text("No thanks")', 'a:has-text("Skip")',
                    'a:has-text("Cancel")', 'a:has-text("No, thanks")',
                    # MS decline/skip buttons (NEVER accept — skip prompts must always refuse)
                    '#declineButton', '#iCancel', '#iShowSkip',
                    'button:has-text("Stay signed out")',
                    # Exact text match for "No" in various languages (safe: always declines)
                    'button:text-is("No")',    # English exact
                    'button:text-is("Нет")',   # Russian exact
                    'button:text-is("Nein")',  # German exact
                    'button:text-is("Non")',   # French exact
                    # MS "Don't show this again" checkbox
                    'input[name="DontShowAgain"]',
                    # MS "Other ways to sign in" link to bypass passkey
                    'a:has-text("Other ways to sign in")',
                    'a:has-text("Sign in with password")',
                ]:
                    try:
                        el = page.locator(sel)
                        if await el.count() > 0 and await el.is_visible():
                            await el.click()
                            await asyncio.sleep(2)
                            skip_clicked = True
                            break
                    except Exception:
                        continue
            if not skip_clicked:
                break

        # ── Verify success — navigate to inbox ──
        _tlog["current_step"] = "Verifying inbox access..."
        try:
            await page.goto(config["inbox_url"], wait_until="domcontentloaded", timeout=25000)
            await asyncio.sleep(random.uniform(4, 7))
        except Exception as e:
            logger.warning(f"[Validator] T-{thread_idx+1} {email}: inbox navigation error: {e}")

        final_url = page.url.lower()
        await debug_screenshot(page, f"val_{provider}_inbox_{safe_email}")

        # Check success
        login_success = any(ind in final_url for ind in config["inbox_indicators"])

        # If redirected back to login — fail
        if any(fi in final_url for fi in config.get("fail_indicators", [])):
            login_success = False

        if not login_success:
            _tlog["current_step"] = f"Login failed — URL: {final_url[:60]}"
            logger.info(f"[Validator] T-{thread_idx+1} {email}: login failed on {provider}, URL: {final_url[:80]}")
            await context.close()
            return False

        # ── SUCCESS — Save account + session + fingerprint ──
        _tlog["current_step"] = "Login OK! Saving profile..."
        logger.info(f"[Validator] T-{thread_idx+1} ✓ {email}: {provider} login successful!")

        try:
            existing = db.query(Account).filter(Account.email == email).first()
            if existing:
                existing.password = password
                existing.status = AccountStatus.NEW
                if recovery:
                    existing.recovery_email = recovery
                existing.provider = provider
                db.commit()
                account = existing
            else:
                account = Account(
                    email=email,
                    password=password,
                    recovery_email=recovery,
                    provider=provider,
                    status=AccountStatus.NEW,
                    geo=proxy.geo if proxy and hasattr(proxy, 'geo') else None,
                    birth_ip=f"{proxy.host}" if proxy and hasattr(proxy, 'host') else None,
                )
                db.add(account)
                db.commit()
                db.refresh(account)

            # Save session
            if save_session_flag:
                try:
                    account.browser_profile_path = await browser_manager.save_session(context, account.id)
                    db.commit()
                    logger.info(f"[Validator] Session saved for {email} (account {account.id})")
                except Exception as se:
                    logger.warning(f"[Validator] Session save error for {email}: {se}")

                # Save fingerprint
                try:
                    fp_data = getattr(context, '_leomail_fingerprint', None)
                    if fp_data:
                        browser_manager.save_fingerprint(account.id, fp_data)
                        account.user_agent = fp_data.get("user_agent", "")
                        db.commit()
                except Exception as fp_err:
                    logger.warning(f"[Validator] Fingerprint save error for {email}: {fp_err}")

            # Add to farm
            if farm_id:
                try:
                    db.execute(
                        farm_accounts.insert().values(farm_id=farm_id, account_id=account.id)
                    )
                    db.commit()
                except Exception:
                    db.rollback()

        except Exception as db_err:
            logger.error(f"[Validator] DB error saving {email}: {db_err}")
            db.rollback()

        await context.close()
        return True

    except ProxyError:
        # Proxy error — re-raise so worker retry loop can handle it
        if context:
            try:
                await context.close()
            except Exception:
                pass
        raise  # Worker will catch ProxyError and retry

    except Exception as e:
        err_str = str(e).lower()
        # Check if this is actually a proxy error disguised as a generic exception
        if any(x in err_str for x in ["err_proxy", "err_tunnel", "err_connection",
                                       "connection_closed", "connection_refused",
                                       "net::err", "chrome-error"]):
            if context:
                try:
                    await context.close()
                except Exception:
                    pass
            raise ProxyError(f"Proxy error during validation: {e}")

        logger.error(f"[Validator] T-{thread_idx+1} Browser error for {email} ({provider}): {e}", exc_info=True)
        if context:
            try:
                if page:
                    await debug_screenshot(page, f"val_{provider}_error_{safe_email}")
            except Exception:
                pass
            try:
                await context.close()
            except Exception:
                pass
        return False


# ─── Helper Functions ───────────────────────────────────────────────────────
async def _find_element(page, selectors: list):
    """Try multiple selectors, return first visible element or None."""
    for sel in selectors:
        try:
            el = page.locator(sel)
            if await el.count() > 0 and await el.is_visible():
                return el
        except Exception:
            continue
    return None


async def _click_any(page, selectors: list) -> bool:
    """Try to click any of the given selectors. Returns True if clicked."""
    for sel in selectors:
        try:
            el = page.locator(sel)
            if await el.count() > 0 and await el.is_visible():
                await el.click()
                return True
        except Exception:
            continue
    # Fallback: Enter key
    try:
        await page.keyboard.press("Enter")
    except Exception:
        pass
    return False


async def _get_page_text(page) -> str:
    """Get page body text (lowercased), safely."""
    try:
        return (await page.locator('body').inner_text(timeout=3000))[:2000].lower()
    except Exception:
        return ""

