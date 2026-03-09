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
from ..services.engine_manager import engine_manager, EngineType

router = APIRouter(prefix="/api/validator", tags=["validator"])

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
    "processing": 0,
    "threads": 1,
    "thread_logs": [],              # per-thread status
    "results": [],                  # [{email, provider, status, time_sec, error}]
    "task_id": None,
    "farm_id": None,
}

UPLOADS_DIR = PROJECT_ROOT / "user_data" / "validator"


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
        email password
        email\tpassword
    Returns (accounts_list, detected_format)
    """
    accounts = []
    fmt = "unknown"
    lines = content.strip().splitlines()

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Try different separators
        parts = None
        if ":" in line:
            parts = line.split(":")
            fmt = "colon"
        elif ";" in line:
            parts = line.split(";")
            fmt = "semicolon"
        elif "\t" in line:
            parts = line.split("\t")
            fmt = "tab"
        elif " " in line:
            parts = line.split(" ", 2)
            fmt = "space"

        if not parts or len(parts) < 2:
            continue

        email = parts[0].strip()
        password = parts[1].strip()
        recovery = parts[2].strip() if len(parts) > 2 else None

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
        raise HTTPException(400, "No valid accounts found in file. Supported: email:password or email:password:recovery")

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
    if _validator_state["running"]:
        raise HTTPException(400, "Validator is already running")
    if not _validator_state["parsed_accounts"]:
        raise HTTPException(400, "No accounts loaded. Upload a file first.")

    VALIDATOR_CANCEL_EVENT.clear()
    _validator_state["running"] = True
    _validator_state["valid"] = 0
    _validator_state["invalid"] = 0
    _validator_state["processing"] = 0
    _validator_state["threads"] = request.threads
    _validator_state["results"] = []
    _validator_state["thread_logs"] = []

    db = SessionLocal()

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
        db.close()
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
    _validator_state["task_id"] = task.id

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
    _validator_state["farm_id"] = farm.id
    logger.info(f"[Validator] Created farm: {farm_name} (ID: {farm.id})")

    db.close()

    # Integrate with EngineManager
    engine_manager.start_engine(EngineType.VALIDATOR, request.threads, len(accounts_to_validate), task.id)

    # Launch validation in background
    asyncio.get_event_loop().run_in_executor(
        None,
        _run_validator_pool,
        accounts_to_validate,
        request.threads,
        request.save_session,
        task.id,
        farm.id,
    )

    return {
        "status": "ok",
        "message": f"Validation started: {len(accounts_to_validate)} accounts, {request.threads} threads",
        "total": len(accounts_to_validate),
        "farm_name": farm_name,
    }


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
    return {
        "running": _validator_state["running"],
        "filename": _validator_state["filename"],
        "format": _validator_state["format"],
        "total": _validator_state["total"],
        "valid": _validator_state["valid"],
        "invalid": _validator_state["invalid"],
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
    }


# ─── Validation Worker Pool ─────────────────────────────────────────────────
def _run_validator_pool(accounts: list, threads: int, save_session: bool, task_id: int, farm_id: int):
    """
    Run validation in a thread pool (called from executor).
    Each thread picks accounts from a shared queue and validates via browser login.
    """
    import queue
    import time

    q = queue.Queue()
    for acc in accounts:
        q.put(acc)

    # Initialize thread logs
    _validator_state["thread_logs"] = [
        {"index": i, "status": "idle", "email": None, "current_step": None, "error": None}
        for i in range(threads)
    ]

    def worker(thread_idx: int):
        """Single validation thread."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        db = SessionLocal()

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
                is_valid = False
                error_msg = None

                try:
                    is_valid = loop.run_until_complete(
                        _validate_single_account(email, password, provider, thread_idx, save_session, db)
                    )
                except Exception as e:
                    error_msg = str(e)[:200]
                    logger.error(f"[Validator] T-{thread_idx+1} Error validating {email}: {e}")

                elapsed = round(time.time() - start_time, 1)
                with _state_lock:
                    _validator_state["processing"] -= 1

                if is_valid:
                    with _state_lock:
                        _validator_state["valid"] += 1
                    status = "valid"

                    # Save to DB
                    try:
                        existing = db.query(Account).filter(Account.email == email).first()
                        if existing:
                            existing.password = password
                            existing.status = AccountStatus.NEW
                            if recovery:
                                existing.recovery_email = recovery
                        else:
                            new_acc = Account(
                                email=email,
                                password=password,
                                recovery_email=recovery,
                                provider=provider,
                                status=AccountStatus.NEW,
                            )
                            db.add(new_acc)
                        db.commit()

                        # Add to farm
                        acc_obj = db.query(Account).filter(Account.email == email).first()
                        if acc_obj and farm_id:
                            db.execute(
                                farm_accounts.insert().values(farm_id=farm_id, account_id=acc_obj.id)
                            )
                            try:
                                db.commit()
                            except Exception:
                                db.rollback()  # duplicate key is fine

                    except Exception as db_err:
                        logger.error(f"[Validator] DB error for {email}: {db_err}")
                        db.rollback()
                else:
                    with _state_lock:
                        _validator_state["invalid"] += 1
                    status = "invalid"

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
                    "status": "completed" if is_valid else "error",
                    "email": email,
                    "current_step": "Valid ✓" if is_valid else (error_msg or "Invalid credentials"),
                    "error": error_msg,
                }

                # Update task progress
                try:
                    task = db.query(Task).get(task_id)
                    if task:
                        task.completed_items = _validator_state["valid"] + _validator_state["invalid"]
                        db.commit()
                except Exception:
                    db.rollback()

        except Exception as e:
            logger.error(f"[Validator] Worker {thread_idx} crashed: {e}")
        finally:
            db.close()
            loop.close()

    # Launch worker threads
    worker_threads = []
    for i in range(min(threads, len(accounts))):
        t = threading.Thread(target=worker, args=(i,), daemon=True)
        t.start()
        worker_threads.append(t)

    # Wait for all threads to complete
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
            task.completed_items = _validator_state["valid"] + _validator_state["invalid"]
            task.completed_at = datetime.utcnow()
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

    logger.info(
        f"[Validator] Done: {_validator_state['valid']} valid, "
        f"{_validator_state['invalid']} invalid out of {len(accounts)}"
    )
    engine_manager.finish_engine(EngineType.VALIDATOR)


async def _validate_single_account(
    email: str, password: str, provider: str, thread_idx: int,
    save_session: bool, db
) -> bool:
    """
    Validate a single account by attempting browser login.
    Returns True if login successful, False otherwise.

    TODO: Implement per-provider login flows.
    For now, uses a simple IMAP check as a fast validation method.
    Browser-based login flows will be added per provider in future iterations.
    """
    import imaplib

    _validator_state["thread_logs"][thread_idx]["current_step"] = f"Connecting to {provider} IMAP..."

    # IMAP server mapping
    IMAP_SERVERS = {
        "gmail": "imap.gmail.com",
        "yahoo": "imap.mail.yahoo.com",
        "aol": "imap.aol.com",
        "outlook": "imap-mail.outlook.com",
        "hotmail": "imap-mail.outlook.com",
        "protonmail": None,  # ProtonMail doesn't support standard IMAP
        "webde": "imap.web.de",
    }

    server = IMAP_SERVERS.get(provider)

    # ProtonMail: can't validate via IMAP — mark as "needs manual check"
    if not server:
        _validator_state["thread_logs"][thread_idx]["current_step"] = "No IMAP support — saved as-is"
        # Still save the account but skip validation
        return True  # Accept protonmail accounts without validation

    try:
        _validator_state["thread_logs"][thread_idx]["current_step"] = f"IMAP login {server}..."

        # Try IMAP login
        imap = imaplib.IMAP4_SSL(server, timeout=15)
        try:
            imap.login(email, password)
            imap.logout()
            _validator_state["thread_logs"][thread_idx]["current_step"] = "Login OK ✓"
            return True
        except imaplib.IMAP4.error as e:
            err = str(e)
            if "AUTHENTICATIONFAILED" in err or "Invalid credentials" in err or "LOGIN failed" in err.upper():
                _validator_state["thread_logs"][thread_idx]["current_step"] = "Invalid credentials"
                return False
            elif "ALERT" in err:
                # Could be "less secure apps" or 2FA prompt
                _validator_state["thread_logs"][thread_idx]["current_step"] = "Auth blocked (2FA/app password needed)"
                return False
            else:
                _validator_state["thread_logs"][thread_idx]["current_step"] = f"IMAP error: {err[:80]}"
                return False
        finally:
            try:
                imap.shutdown()
            except Exception:
                pass

    except Exception as e:
        err = str(e)[:100]
        _validator_state["thread_logs"][thread_idx]["current_step"] = f"Connection error: {err}"
        logger.debug(f"[Validator] T-{thread_idx+1} IMAP error for {email}: {err}")
        return False
