"""
Leomail v3 — Birth Router
Pooled registration of Gmail/Outlook accounts with captcha, SMS, profiles.
"""
from fastapi import APIRouter, Depends, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database import get_db, SessionLocal
from ..models import Proxy, ProxyStatus, Task, TaskStatus, Account, Farm, ThreadLog
from ..modules.browser_manager import BrowserManager
from ..services.captcha_provider import CaptchaProvider
from ..services.sms_provider import GrizzlySMS
from ..services.simsms_provider import SimSmsProvider
from ..services.proxy_manager import ProxyManager
from ..utils import generate_birthday, generate_password, generate_username
from ..modules.human_behavior import (
    random_mouse_move, random_scroll, between_steps,
    pre_registration_warmup, human_click, warmup_browsing,
)
from ..models import Farm, Account, Proxy, Task, ThreadLog, TaskStatus, NamePack
from ..config import load_config, get_api_key
from loguru import logger
import asyncio
import random
from datetime import datetime
from pathlib import Path
import json

# === Provider registration engines (extracted to modules/birth/) ===
from ..modules.birth.outlook import register_single_outlook
from ..modules.birth.gmail import register_single_gmail
from ..modules.birth.yahoo import register_single_yahoo
from ..modules.birth.aol import register_single_aol
from ..modules.birth._helpers import get_sms_provider as _get_sms_provider
from ..modules.birth._helpers import get_captcha_provider as _get_captcha_provider

router = APIRouter(prefix="/api/birth", tags=["birth"])

# Global registry for active browser pages — allows screenshot/control from UI
ACTIVE_PAGES: dict[int, dict] = {}  # thread_log_id -> {"page": Page, "context": ctx}

# Global cancel flag for birth tasks
BIRTH_CANCEL: set = set()  # Set of task_ids to cancel

# Global cancel event — interrupts blocking SMS waits instantly
import threading
BIRTH_CANCEL_EVENT = threading.Event()


class BirthRequest(BaseModel):
    provider: str = "outlook"  # gmail, outlook
    quantity: int = 1
    device_type: str = "desktop"  # desktop, phone_android, phone_ios
    name_pack_ids: list[int] = []
    sms_provider: str = "simsms"  # simsms, grizzly
    sms_countries: list[str] = []  # allowed countries, empty = auto
    threads: int = 1
    farm_name: str = ""  # auto-generated if empty
    headless: bool = True  # False = visible browser window on server



async def run_birth_task(request: BirthRequest):
    """Run birth registration pool."""
    # Clear previous cancel signals
    BIRTH_CANCEL_EVENT.clear()
    db = SessionLocal()
    try:
        # Create task record
        task = Task(
            type="birth",
            status=TaskStatus.RUNNING,
            total_items=request.quantity,
            thread_count=request.threads,
            details=f"Registering {request.quantity} {request.provider} accounts",
        )
        db.add(task)
        db.commit()

        # Get proxy pool — filter by device type + provider usage limit (NO FALLBACK)
        proxy_manager = ProxyManager(db)
        proxy_pool = proxy_manager.get_proxy_pool(
            request.quantity,
            device_type=request.device_type,
            provider=request.provider,
            max_per_provider=3,
        )
        logger.info(f"[Birth] Proxy pool: {len(proxy_pool)} proxies for device={request.device_type}, provider={request.provider}")

        if not proxy_pool:
            device_label = "MOBILE" if request.device_type.startswith("phone") else "SOCKS5/HTTP"
            task = Task(type="birth", status=TaskStatus.STOPPED, total_items=request.quantity,
                        stop_reason=f"Процесс завершился потому что — нет подходящих прокси ({device_label}) для {request.provider}. Загрузите прокси нужного типа или сбросьте счётчики.")
            db.add(task); db.commit()
            return {"status": "error", "message": task.stop_reason}

        # Create farm — auto-generate descriptive name: Date - Provider - GEO(names) - Lvl0
        if request.farm_name:
            farm_name = request.farm_name
        else:
            date_str = datetime.now().strftime('%Y.%m.%d')
            provider_label = request.provider.capitalize()
            # GEO from name packs (language/region of names), NOT proxy geo
            geo_label = "MIX"
            if request.name_pack_ids:
                name_packs_for_label = db.query(NamePack).filter(NamePack.id.in_(request.name_pack_ids)).all()
                if name_packs_for_label:
                    pack_names = [p.name for p in name_packs_for_label]
                    geo_label = " + ".join(pack_names)[:30]
            farm_name = f"{date_str} - {provider_label} - {geo_label} - Lvl0"
        farm = Farm(name=farm_name, description=f"{request.quantity}x {request.provider}")
        db.add(farm)
        db.commit()

        # Load name pool from selected packs — COMBINATORIAL approach
        # Instead of using fixed (first,last) pairs, we collect ALL first names
        # and ALL last names separately, then combine randomly for near-infinite variations.
        # Example: 500 firsts × 500 lasts = 250,000 unique name combinations
        all_first_names = set()
        all_last_names = set()
        if request.name_pack_ids:
            import os
            packs = db.query(NamePack).filter(NamePack.id.in_(request.name_pack_ids)).all()
            logger.info(f"[Birth] Found {len(packs)} name packs for IDs: {request.name_pack_ids}")
            for pack in packs:
                file_path = pack.file_path
                logger.info(f"[Birth] Pack '{pack.name}': file_path={file_path}, exists={os.path.exists(file_path)}")
                
                # Try resolving path if not found
                if not os.path.exists(file_path):
                    alt_path = os.path.join("user_data", "names", os.path.basename(file_path))
                    if os.path.exists(alt_path):
                        file_path = alt_path
                        logger.info(f"[Birth] Resolved to: {alt_path}")
                
                if os.path.exists(file_path):
                    with open(file_path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line or line.startswith('#'):
                                continue
                            if ',' in line:
                                parts = [p.strip() for p in line.split(',', 1)]
                            elif '\t' in line:
                                parts = [p.strip() for p in line.split('\t', 1)]
                            else:
                                parts = line.split(None, 1)
                            if parts:
                                first = parts[0]
                                last = parts[1] if len(parts) > 1 else ""
                                all_first_names.add(first)
                                if last:
                                    all_last_names.add(last)
                else:
                    logger.error(f"[Birth] ❌ Файл пакета имён не найден: {file_path}")

        # Convert to lists for random access
        first_names_list = list(all_first_names)
        last_names_list = list(all_last_names) if all_last_names else [""]
        combos = len(first_names_list) * len(last_names_list)
        logger.info(f"[Birth] Name pool: {len(first_names_list)} firsts × {len(last_names_list)} lasts = {combos} possible combinations")

        # Build name_pool with random combinatorial pairs (much larger than original)
        # Generate enough unique pairs for the registration request + buffer
        name_pool = []
        needed = max(request.quantity * 4, 200)
        used_combos = set()
        for _ in range(needed):
            for _attempt in range(10):  # avoid infinite loop
                fn = random.choice(first_names_list)
                ln = random.choice(last_names_list)
                combo = (fn, ln)
                if combo not in used_combos:
                    used_combos.add(combo)
                    name_pool.append(combo)
                    break
            else:
                # If we exhausted unique combos, allow repeats
                name_pool.append((random.choice(first_names_list), random.choice(last_names_list)))

        random.shuffle(name_pool)

        # Get providers
        captcha = _get_captcha_provider()
        sms = _get_sms_provider(request.sms_provider)

        # CRITICAL: Abort if no names loaded
        if not name_pool or not first_names_list:
            logger.error(f"[Birth] ❌ Пакет имён пуст или не выбран! Регистрация невозможна.")
            task.status = TaskStatus.STOPPED
            task.stop_reason = "Процесс завершился потому что — пакет имён пуст или не выбран"
            db.commit()
            return

        # Start browser
        browser_manager = BrowserManager(headless=True)
        await browser_manager.start()

        # REQUIRE proxies — registration without proxy is forbidden
        if not proxy_pool:
            logger.error("[Birth] ❌ No proxies available! Registration requires at least 1 proxy.")
            task.status = TaskStatus.STOPPED
            task.stop_reason = "Процесс завершился потому что — нет прокси для регистрации"
            db.commit()
            return

        try:
            registered_accounts = []
            max_attempts = request.quantity * 4  # fail-safe
            attempt_counter = [0]
            success_counter = [0]
            name_index = [0]  # Atomic index into shuffled name pool
            job_lock = asyncio.Lock()
            # Smart retry: shared blacklists across workers
            country_blacklist = set()  # countries that failed SMS
            proxy_blacklist = set()    # proxy IDs that got E500/banned
            consecutive_failures = [0]  # stop task after 10 in a row

            async def worker(worker_id: int):
                """Worker keeps registering until target reached."""
                while True:
                    async with job_lock:
                        if success_counter[0] >= request.quantity:
                            return
                        if attempt_counter[0] >= max_attempts:
                            task.stop_reason = f"Процесс завершился потому что — достигнут лимит попыток ({max_attempts}). Зарегистрировано {success_counter[0]} из {request.quantity}"
                            return
                        if consecutive_failures[0] >= 10:
                            task.stop_reason = f"Процесс завершился потому что — 10 ошибок подряд. Зарегистрировано {success_counter[0]} из {request.quantity}. Проверьте прокси."
                            return
                        attempt_counter[0] += 1
                        current_attempt = attempt_counter[0]

                    # Check if cancelled
                    if task.id in BIRTH_CANCEL:
                        logger.info(f"[Birth] Worker {worker_id}: task cancelled by user")
                        return

                    # Check if task cancelled via DB
                    try:
                        db.refresh(task)
                        if task.status == TaskStatus.FAILED:
                            return
                    except Exception:
                        pass

                    thread_log = None
                    try:
                        # Get a verified proxy (excluding blacklisted/burned ones)
                        proxy = await proxy_manager.get_verified_unbound_proxy_async(
                            exclude_ids=proxy_blacklist
                        )
                        if not proxy and proxy_pool:
                            logger.warning(f"[Birth] Worker {worker_id}: no free proxy, waiting...")
                            await asyncio.sleep(5)
                            continue

                        # Increment per-provider usage counter
                        if proxy:
                            proxy_manager.increment_provider_usage(proxy, request.provider)

                        thread_log = ThreadLog(
                            task_id=task.id,
                            thread_index=current_attempt - 1,
                            thread_type="birth",
                            status="running",
                            proxy_info=proxy.to_string() if proxy else "No proxy",
                        )
                        thread_log._worker_id = worker_id  # For log labels
                        db.add(thread_log)
                        db.commit()

                        # Pop unique name from pool (under lock)
                        async with job_lock:
                            idx = name_index[0] % len(name_pool)
                            name_pair = name_pool[idx]
                            name_index[0] += 1
                        worker_name_pool = [name_pair]

                        # Inject SMS country: proxy GEO takes priority
                        if sms:
                            if proxy and getattr(proxy, 'geo', None):
                                sms._sms_countries = [proxy.geo.lower()]
                            elif request.sms_countries:
                                sms._sms_countries = request.sms_countries
                            sms._country_blacklist = country_blacklist

                        account = None
                        if request.provider == "outlook":
                            account = await register_single_outlook(
                                browser_manager, proxy, request.device_type,
                                worker_name_pool, captcha, db, thread_log,
                                ACTIVE_PAGES=ACTIVE_PAGES,
                            )
                        elif request.provider == "hotmail":
                            account = await register_single_outlook(
                                browser_manager, proxy, request.device_type,
                                worker_name_pool, captcha, db, thread_log,
                                domain="hotmail.com",
                                ACTIVE_PAGES=ACTIVE_PAGES,
                            )
                        elif request.provider == "gmail":
                            if not sms:
                                thread_log.status = "error"
                                thread_log.error_message = "Gmail требует SMS провайдер"
                                db.commit()
                                return
                            account = await register_single_gmail(
                                browser_manager, proxy, worker_name_pool,
                                captcha, sms, db, thread_log,
                                ACTIVE_PAGES=ACTIVE_PAGES,
                                BIRTH_CANCEL_EVENT=BIRTH_CANCEL_EVENT,
                            )
                        elif request.provider == "yahoo":
                            if not sms:
                                thread_log.status = "error"
                                thread_log.error_message = "Yahoo требует SMS провайдер"
                                db.commit()
                                return
                            account = await register_single_yahoo(
                                browser_manager, proxy, request.device_type,
                                worker_name_pool, sms, db, thread_log,
                                captcha_provider=captcha,
                                ACTIVE_PAGES=ACTIVE_PAGES,
                                BIRTH_CANCEL_EVENT=BIRTH_CANCEL_EVENT,
                            )
                        elif request.provider == "aol":
                            if not sms:
                                thread_log.status = "error"
                                thread_log.error_message = "AOL требует SMS провайдер"
                                db.commit()
                                return
                            account = await register_single_aol(
                                browser_manager, proxy, request.device_type,
                                worker_name_pool, sms, db, thread_log,
                                captcha_provider=captcha,
                                ACTIVE_PAGES=ACTIVE_PAGES,
                                BIRTH_CANCEL_EVENT=BIRTH_CANCEL_EVENT,
                            )
                        else:
                            thread_log.status = "error"
                            thread_log.error_message = f"Провайдер '{request.provider}' не поддерживается"
                            db.commit()
                            return

                        if account:
                            # Bind proxy permanently to account
                            if proxy:
                                proxy_manager.bind_proxy_to_account(proxy, account)

                            farm.accounts.append(account)
                            thread_log.status = "done"
                            thread_log.account_email = account.email

                            async with job_lock:
                                registered_accounts.append(account)
                                success_counter[0] += 1
                                consecutive_failures[0] = 0  # reset on success
                                task.completed_items = success_counter[0]

                            db.commit()
                            logger.info(f"[Birth] ✅ Worker {worker_id}: {account.email} "
                                        f"({success_counter[0]}/{request.quantity})")
                        else:
                            task.failed_items = (task.failed_items or 0) + 1
                            async with job_lock:
                                consecutive_failures[0] += 1
                            thread_log.status = "error"
                            if not thread_log.error_message:
                                thread_log.error_message = "Регистрация не завершена"

                            # Smart retry: blacklist proxy if E500/IP blocked
                            err_msg = (thread_log.error_message or "").lower()
                            if proxy and ("ip" in err_msg or "e500" in err_msg or "заблокирован" in err_msg):
                                proxy_blacklist.add(proxy.id)
                                logger.info(f"[Birth] Proxy {proxy.host} blacklisted for this task")

                            # Smart retry: blacklist country if SMS actually timed out
                            # (NOT for "no numbers" or user cancel — only real delivery failure)
                            if sms and hasattr(sms, '_last_country') and sms._last_country:
                                sms_countries_list = getattr(sms, '_sms_countries', []) or []
                                # Don't blacklist if only 1 country selected — nowhere else to go
                                if len(sms_countries_list) > 1:
                                    # Only blacklist on actual SMS delivery timeout, not other errors
                                    if "таймаут" in err_msg and "sms не получено" in err_msg:
                                        country_blacklist.add(sms._last_country)
                                        logger.info(f"[Birth] Country '{sms._last_country}' blacklisted (SMS timeout)")

                            db.commit()
                            logger.info(f"[Birth] ❌ Worker {worker_id}: attempt {current_attempt} failed, retrying...")
                            await asyncio.sleep(random.uniform(2, 5))

                    except Exception as e:
                        logger.error(f"[Birth] Worker {worker_id} crashed: {e}", exc_info=True)
                        try:
                            task.failed_items = (task.failed_items or 0) + 1
                            async with job_lock:
                                consecutive_failures[0] += 1
                            if thread_log:
                                thread_log.status = "error"
                                thread_log.error_message = str(e)[:500]
                            db.commit()
                        except Exception:
                            pass
                        await asyncio.sleep(3)

            # Launch workers
            num_workers = min(request.threads, request.quantity)
            worker_tasks = [asyncio.create_task(worker(i)) for i in range(num_workers)]
            await asyncio.gather(*worker_tasks, return_exceptions=True)

            # Determine final status
            if task.stop_reason:
                task.status = TaskStatus.STOPPED
            elif success_counter[0] >= request.quantity:
                task.status = TaskStatus.COMPLETED
            else:
                task.status = TaskStatus.STOPPED
                task.stop_reason = f"Процесс завершился потому что — зарегистрировано {success_counter[0]} из {request.quantity} (остальные — ошибки)"
            task.completed_at = datetime.utcnow()
            db.commit()

            logger.info(f"Birth complete: {len(registered_accounts)}/{request.quantity} registered, farm: {farm_name}")

        finally:
            await browser_manager.stop()

    except Exception as e:
        logger.error(f"Birth task failed: {e}")
        if task and task.id:
            try:
                task.status = TaskStatus.FAILED
                task.stop_reason = f"Процесс завершился потому что — критическая ошибка: {str(e)[:200]}"
                task.completed_at = datetime.utcnow()
                db.commit()
            except Exception:
                pass
    finally:
        db.close()


@router.post("/start")
async def start_registration(request: BirthRequest, background_tasks: BackgroundTasks):
    """Start account registration in background."""
    background_tasks.add_task(run_birth_task, request)
    return {
        "status": "started",
        "message": f"Starting {request.quantity} {request.provider} registration(s), {request.threads} thread(s)",
    }


SMS_COUNTRY_NAMES = {
    "ru": ("Россия", "🇷🇺"), "ua": ("Украина", "🇺🇦"), "kz": ("Казахстан", "🇰🇿"),
    "cn": ("Китай", "🇨🇳"), "ph": ("Филиппины", "🇵🇭"), "id": ("Индонезия", "🇮🇩"),
    "ke": ("Кения", "🇰🇪"), "br": ("Бразилия", "🇧🇷"), "us": ("США", "🇺🇸"),
    "il": ("Израиль", "🇮🇱"), "pl": ("Польша", "🇵🇱"), "uk": ("Англия", "🇬🇧"),
    "us_v": ("США Virtual", "🇺🇸"), "ng": ("Нигерия", "🇳🇬"), "eg": ("Египет", "🇪🇬"),
    "fr": ("Франция", "🇫🇷"), "ie": ("Ирландия", "🇮🇪"), "za": ("ЮАР", "🇿🇦"),
    "ro": ("Румыния", "🇷🇴"), "se": ("Швеция", "🇸🇪"), "ee": ("Эстония", "🇪🇪"),
    "ca": ("Канада", "🇨🇦"), "de": ("Германия", "🇩🇪"), "nl": ("Нидерланды", "🇳🇱"),
    "at": ("Австрия", "🇦🇹"), "th": ("Таиланд", "🇹🇭"), "mx": ("Мексика", "🇲🇽"),
    "es": ("Испания", "🇪🇸"), "tr": ("Турция", "🇹🇷"), "cz": ("Чехия", "🇨🇿"),
    "pe": ("Перу", "🇵🇪"), "nz": ("Н. Зеландия", "🇳🇿"),
}


@router.get("/sms-countries")
async def get_sms_countries():
    """Return available SMS countries from SimSMS."""
    from backend.services.simsms_provider import COUNTRY_CODES
    countries = []
    for code in COUNTRY_CODES:
        name, flag = SMS_COUNTRY_NAMES.get(code, (code, "🏳️"))
        countries.append({"code": code, "name": name, "flag": flag})
    return {"countries": countries}


@router.get("/status")
async def birth_status(db: Session = Depends(get_db)):
    """Check if any birth task is currently running. Used by frontend for stop button."""
    running_task = db.query(Task).filter(
        Task.type == "birth",
        Task.status == TaskStatus.RUNNING,
    ).order_by(Task.created_at.desc()).first()

    if running_task:
        return {
            "running": True,
            "task_id": running_task.id,
            "total": running_task.total_items or 0,
            "completed": running_task.completed_items or 0,
            "failed": running_task.failed_items or 0,
            "status": "running",
            "stop_reason": running_task.stop_reason,
        }

    # Check last finished task
    last_task = db.query(Task).filter(
        Task.type == "birth",
    ).order_by(Task.created_at.desc()).first()

    if last_task:
        return {
            "running": False,
            "task_id": last_task.id,
            "total": last_task.total_items or 0,
            "completed": last_task.completed_items or 0,
            "failed": last_task.failed_items or 0,
            "status": last_task.status,
            "stop_reason": last_task.stop_reason,
            "error": last_task.details if last_task.status == "failed" else None,
        }

    return {"running": False, "task_id": None}


@router.post("/stop")
async def stop_registration(mode: str = "instant", db: Session = Depends(get_db)):
    """
    Stop birth tasks.
    mode: "instant" = force-kill everything NOW, "graceful" = wait for threads
    """
    running = db.query(Task).filter(
        Task.status == TaskStatus.RUNNING,
        Task.type == "birth",
    ).all()

    stopped = 0
    for t in running:
        BIRTH_CANCEL.add(t.id)
        if mode == "instant":
            t.status = TaskStatus.FAILED
            t.details = "Остановлено пользователем (мгновенно)"
            t.stop_reason = "Остановлено пользователем"
        else:
            t.details = "Остановка: ждём завершения потоков..."
            t.stop_reason = "Остановлено пользователем (ожидание потоков)"
        stopped += 1

    # Signal all blocking SMS waits to abort
    BIRTH_CANCEL_EVENT.set()

    # Mark all running thread logs as stopped
    if mode == "instant":
        threads_running = db.query(ThreadLog).filter(
            ThreadLog.thread_type == "birth", ThreadLog.status == "running",
        ).all()
        for tl in threads_running:
            tl.status = "stopped"
            tl.current_action = "Остановлено"

    db.commit()

    # INSTANT KILL: Force-close all active browser pages/contexts
    # This causes any running Playwright operations (including SMS waits) to throw
    # exceptions immediately, terminating the worker threads
    killed_pages = 0
    if mode == "instant" and ACTIVE_PAGES:
        pages_to_close = list(ACTIVE_PAGES.items())
        ACTIVE_PAGES.clear()
        for thread_id, entry in pages_to_close:
            try:
                page = entry.get("page")
                ctx = entry.get("context")
                if page and not page.is_closed():
                    await page.close()
                if ctx:
                    await ctx.close()
                killed_pages += 1
            except Exception as e:
                logger.debug(f"[Birth] Error closing page {thread_id}: {e}")

    logger.info(f"[Birth] User stopped {stopped} task(s), mode={mode}, killed {killed_pages} browser pages")
    return {"stopped": stopped, "killed_pages": killed_pages}


@router.get("/screenshot/{thread_id}")
async def get_thread_screenshot(thread_id: int):
    """Take a screenshot of an active browser thread."""
    from fastapi.responses import Response
    import base64
    entry = ACTIVE_PAGES.get(thread_id)
    if not entry:
        return {"error": "Поток не найден или браузер закрыт", "active_threads": list(ACTIVE_PAGES.keys())}
    try:
        page = entry["page"]
        screenshot_bytes = await page.screenshot(type="png")
        return Response(content=screenshot_bytes, media_type="image/png")
    except Exception as e:
        return {"error": f"Скриншот не удался: {str(e)[:200]}"}


@router.get("/active-pages")
async def get_active_pages():
    """List all thread IDs with active browser pages."""
    return {"active": list(ACTIVE_PAGES.keys())}


@router.get("/status")
async def get_birth_status(db: Session = Depends(get_db)):
    """Get latest birth task status for frontend polling."""
    # Check for running tasks first
    running_task = db.query(Task).filter(
        Task.type == "birth",
        Task.status == TaskStatus.RUNNING,
    ).order_by(Task.id.desc()).first()

    if running_task:
        return {
            "running": True,
            "task_id": running_task.id,
            "total": running_task.total_items or 0,
            "completed": running_task.completed_items or 0,
            "failed": running_task.failed_items or 0,
            "active_threads": list(ACTIVE_PAGES.keys()),
        }

    # Get latest completed/failed task
    latest = db.query(Task).filter(
        Task.type == "birth",
    ).order_by(Task.id.desc()).first()

    if latest:
        return {
            "running": False,
            "task_id": latest.id,
            "status": latest.status.value if latest.status else "unknown",
            "total": latest.total_items or 0,
            "completed": latest.completed_items or 0,
            "failed": latest.failed_items or 0,
            "error": latest.details,
        }

    return {"running": False, "task_id": None}
