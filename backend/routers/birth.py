"""
Leomail v4 - Birth Router
Pooled registration of Gmail/Outlook accounts with captcha, SMS, profiles.
"""
from fastapi import APIRouter, Depends, BackgroundTasks
import copy
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database import get_db, SessionLocal
from ..models import Proxy, ProxyStatus, Task, TaskStatus, Account, Farm, ThreadLog
from ..modules.browser_manager import BrowserManager
from ..services.captcha_provider import CaptchaProvider
# SMS providers loaded via chain (get_sms_chain), not individual imports
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
from ..modules.birth.protonmail import register_single_protonmail
from ..modules.birth._helpers import get_sms_chain as _get_sms_chain
from ..services.proxy_providers import tiered_auto_buy
from ..modules.birth._helpers import get_captcha_provider as _get_captcha_provider
from ..services.engine_manager import engine_manager, EngineType

router = APIRouter(prefix="/api/birth", tags=["birth"])

# Global registry for active browser pages - allows screenshot/control from UI
ACTIVE_PAGES: dict[int, dict] = {}  # thread_log_id -> {"page": Page, "context": ctx}

# Global cancel flag for birth tasks
BIRTH_CANCEL: set = set()  # Set of task_ids to cancel

# Global cancel event - interrupts blocking SMS waits instantly
import threading
BIRTH_CANCEL_EVENT = threading.Event()


def classify_error(error_message: str) -> str:
    """Classify error message into category for analytics.
    Categories: proxy, captcha, sms, block, page, browser, unknown.
    Uses error codes (E1xx-E5xx) and keyword matching.
    """
    msg = (error_message or "").lower()
    # Captcha failures
    if any(x in msg for x in ["e410", "e411", "e412", "captcha", "funcaptcha",
                               "perimeterx", "px", "hcaptcha", "recaptcha", "captcha_fail"]):
        return "captcha"
    # SMS failures
    if any(x in msg for x in ["sms", "phone", "code not received", "no numbers",
                               "verification code", "verification"]):
        return "sms"
    # Proxy / IP blocks
    if any(x in msg for x in ["e301", "e303", "e304", "e500", "e501", "proxy",
                               "dead", "datacenter", "asn", "connection error",
                               "something went wrong"]):
        return "proxy"
    # Active blocks by provider
    if any(x in msg for x in ["e302", "blocked", "unusual activity", "banned",
                               "can't create", "suspended"]):
        return "block"
    # Page / selector issues
    if any(x in msg for x in ["e101", "e102", "e103", "e104", "e502",
                               "not found", "field", "not confirmed"]):
        return "page"
    # Browser crashes
    if any(x in msg for x in ["browser", "crash", "target closed",
                               "connection closed", "browser has been closed",
                               "context or browser"]):
        return "browser"
    return "unknown"


class BirthRequest(BaseModel):
    provider: str = "outlook"  # gmail, outlook, yahoo, aol, hotmail, protonmail
    quantity: int = 1
    name_pack_ids: list[int] = []
    threads: int = 1
    farm_name: str = ""  # auto-generated if empty
    headless: bool = True  # False = visible browser window on server



async def run_birth_task(request: BirthRequest):
    """Run birth registration pool."""
    # Clear previous cancel signals
    BIRTH_CANCEL_EVENT.clear()
    db = SessionLocal()

    # Register with EngineManager for parallel tracking
    try:
        engine_manager.start_engine(
            EngineType.AUTOREG,
            threads=request.threads,
            total_target=request.quantity,
        )
    except RuntimeError:
        logger.warning("[Birth] Autoreg engine already running")

    try:
        # ── Clean up zombie tasks from previous crashes ──
        stale_tasks = db.query(Task).filter(
            Task.type == "birth", Task.status == TaskStatus.RUNNING
        ).all()
        for st in stale_tasks:
            st.status = TaskStatus.FAILED
            st.stop_reason = "Cleaned up (stale from previous run)"
            logger.info(f"[Birth] Cleaned up stale task #{st.id}")
        if stale_tasks:
            db.commit()

        # Validate provider
        valid_providers = ['yahoo', 'aol', 'outlook', 'hotmail', 'protonmail', 'gmail']
        if request.provider.lower() not in valid_providers:
            return {"status": "error", "message": f"Unknown provider: {request.provider}. Valid: {valid_providers}"}

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

        # Get proxy pool - filter by provider usage limit (NO FALLBACK)
        proxy_manager = ProxyManager(db)
        proxy_pool = proxy_manager.get_proxy_pool(
            request.quantity,
            provider=request.provider,
        )
        logger.info(f"[Birth] Proxy pool: {len(proxy_pool)} proxies for provider={request.provider}")

        if not proxy_pool:
            # ── Auto-recovery: reset counters for this provider and retry ──
            logger.warning(f"[Birth] No proxies for {request.provider} — auto-resetting usage counters...")
            proxy_manager.reset_all_counters()
            proxy_pool = proxy_manager.get_proxy_pool(
                request.quantity, provider=request.provider,
            )
            logger.info(f"[Birth] After counter reset: {len(proxy_pool)} proxies for {request.provider}")

        if not proxy_pool:
            # ── Still empty: try auto-buy from external services ──
            logger.warning(f"[Birth] Still no proxies after reset — attempting auto-buy...")
            try:
                new_proxies = await asyncio.to_thread(
                    tiered_auto_buy,
                    provider=request.provider,
                    count=3,
                    country="us",
                )
                if new_proxies:
                    for np_data in new_proxies:
                        p = Proxy(
                            host=np_data["host"], port=np_data["port"],
                            username=np_data.get("username", ""),
                            password=np_data.get("password", ""),
                            protocol=np_data.get("protocol", "http"),
                            geo=np_data.get("geo", "US"),
                            status=ProxyStatus.ACTIVE,
                            source=np_data.get("source", "auto-buy"),
                        )
                        db.add(p)
                    db.commit()
                    proxy_pool = proxy_manager.get_proxy_pool(
                        request.quantity, provider=request.provider,
                    )
                    logger.info(f"[Birth] Auto-bought {len(new_proxies)} proxies, pool now: {len(proxy_pool)}")
            except Exception as buy_err:
                logger.warning(f"[Birth] Auto-buy failed: {buy_err}")

        if not proxy_pool:
            # ── All recovery failed — stop this task (same task, not a new one) ──
            task.status = TaskStatus.STOPPED
            task.stop_reason = f"No suitable proxies for {request.provider}. Counters were auto-reset. Load new proxies or check proxy health."
            db.commit()
            return {"status": "error", "message": task.stop_reason}

        # Create farm - auto-generate descriptive name: Date - Provider - GEO(names) - Lvl0
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
            farm_name = f"{geo_label} / {provider_label} / {date_str}"

        # Derive country code for auto-buy from name pack
        NAME_TO_GEO = {
            "argentina": "ar", "bolivia": "bo", "brazil": "br", "canada": "ca",
            "chile": "cl", "colombia": "co", "costa rica": "cr", "cuba": "cu",
            "dominican": "do", "ecuador": "ec", "egypt": "eg", "el salvador": "sv",
            "guatemala": "gt", "honduras": "hn", "mexico": "mx", "nicaragua": "ni",
            "nigeria": "ng", "panama": "pa", "paraguay": "py", "peru": "pe",
            "puerto rico": "pr", "south africa": "za", "uruguay": "uy",
            "usa": "us", "venezuela": "ve", "turkey": "tr", "russia": "ru",
            "germany": "de", "france": "fr", "spain": "es", "italy": "it",
            "uk": "gb", "india": "in", "japan": "jp", "china": "cn",
            "arab": "sa", "philippines": "ph",
        }
        auto_buy_geo = "us"  # fallback
        if geo_label and geo_label != "MIX":
            for name_key, code in NAME_TO_GEO.items():
                if name_key in geo_label.lower():
                    auto_buy_geo = code
                    break
        logger.info(f"[Birth] Auto-buy geo: {auto_buy_geo} (from name pack: {geo_label})")

        farm = Farm(name=farm_name, description=f"{request.quantity}x {request.provider}")
        db.add(farm)
        db.commit()

        # Load name pool from selected packs - COMBINATORIAL approach
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
                    logger.error(f"[Birth] [FAIL] Name pack file not found: {file_path}")

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
        # SMS: chain auto-rotation (5sim → grizzly → simsms), no manual selection
        has_sms_chain = bool(_get_sms_chain())

        # CRITICAL: Abort if no names loaded
        if not name_pool or not first_names_list:
            logger.error(f"[Birth] [FAIL] Name pack empty or not selected! Registration impossible.")
            task.status = TaskStatus.STOPPED
            task.stop_reason = "Process stopped - name pack empty or not selected"
            db.commit()
            return

        # Start browser
        browser_manager = BrowserManager(headless=False)
        await browser_manager.start()

        # REQUIRE proxies - registration without proxy is forbidden
        if not proxy_pool:
            logger.error("[Birth] [FAIL] No proxies available! Registration requires at least 1 proxy.")
            task.status = TaskStatus.STOPPED
            task.stop_reason = "Process stopped - no proxies for registration"
            db.commit()
            return

        try:
            registered_accounts = []
            success_counter = [0]
            name_index = [0]  # Atomic index into shuffled name pool
            job_lock = asyncio.Lock()
            proxy_select_lock = asyncio.Lock()  # Serialize proxy selection — prevents 2 workers getting same proxy
            proxies_in_use = set()  # Track proxy IDs currently being used by active workers
            # Smart retry: shared blacklists across workers
            country_blacklist = set()  # countries that failed SMS
            proxy_blacklist = set()    # proxy IDs that got E500/banned
            consecutive_failures = [0]  # stop task after 30 in a row (with cooldown at 15)
            # ── Resource Exhaustion Tracking (2 rounds = stop) ──
            # Each counter tracks consecutive failures caused by a specific resource.
            # After 2 full rounds through all providers of that resource type → stop.
            sms_round_fails = [0]      # consecutive SMS failures
            captcha_round_fails = [0]  # consecutive CAPTCHA failures
            proxy_round_fails = [0]    # consecutive proxy failures
            SMS_MAX_ROUNDS = 6         # 2 rounds × 3 SMS providers
            CAPTCHA_MAX_ROUNDS = 6     # 2 rounds × 3 captcha providers
            PROXY_MAX_ROUNDS = 8       # 2 rounds × 4 proxy tiers

            async def worker(worker_id: int):
                """Worker keeps registering until target reached — NO attempt limit."""
                while True:
                    needs_cooldown = False
                    async with job_lock:
                        if success_counter[0] >= request.quantity:
                            return
                        if consecutive_failures[0] >= 30:
                            task.stop_reason = f"Process stopped because - 30 errors in a row. Registered {success_counter[0]} of {request.quantity}. Check proxies and SMS."
                            return
                        if consecutive_failures[0] >= 15 and consecutive_failures[0] % 15 == 0:
                            needs_cooldown = True
                            logger.warning(f"[Birth] Worker {worker_id}: {consecutive_failures[0]} failures, cooldown 60s...")

                    # Cooldown OUTSIDE lock so other workers can continue
                    if needs_cooldown:
                        await asyncio.sleep(60)

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
                    proxy = None  # Track for finally block
                    try:
                        # Get a verified proxy (excluding blacklisted/burned AND currently in-use ones)
                        async with proxy_select_lock:
                            proxy = await proxy_manager.get_verified_unbound_proxy_async(
                                exclude_ids=proxy_blacklist | proxies_in_use,
                                provider=request.provider,
                            )
                            if proxy:
                                proxies_in_use.add(proxy.id)
                        if not proxy:
                            # NEVER GIVE UP — auto-buy and retry until user cancels
                            # Check cancel first
                            if task.id in BIRTH_CANCEL:
                                return
                            if proxy_blacklist or not proxy_pool:
                                # All proxies blacklisted or pool empty — auto-buy residential
                                logger.warning(f"[Birth] Worker {worker_id}: no usable proxies "
                                              f"(blacklisted={len(proxy_blacklist)}, pool={len(proxy_pool)}), auto-buying residential...")
                                bought_any = False
                                for buy_attempt in range(3):  # 3 auto-buy attempts
                                    if task.id in BIRTH_CANCEL:
                                        return
                                    try:
                                        new_proxies = await asyncio.to_thread(
                                            tiered_auto_buy,
                                            provider=request.provider,
                                            count=3,
                                            country=auto_buy_geo,
                                        )
                                        if new_proxies:
                                            for np in new_proxies:
                                                p = Proxy(
                                                    host=np["host"], port=np["port"],
                                                    username=np.get("username", ""),
                                                    password=np.get("password", ""),
                                                    protocol=np.get("protocol", "http"),
                                                    proxy_type=np.get("proxy_type", "residential"),
                                                    geo=np.get("geo", "US"),
                                                    status=ProxyStatus.ACTIVE,
                                                    external_id=np.get("external_id", ""),
                                                    source=np.get("source", "auto-buy"),
                                                )
                                                db.add(p)
                                                db.commit()
                                                proxy_pool.append(p)
                                            proxy_blacklist.clear()
                                            bought_any = True
                                            logger.info(f"[Birth] Auto-bought {len(new_proxies)} residential proxies, retrying...")
                                            break
                                    except Exception as e:
                                        logger.warning(f"[Birth] Auto-buy attempt {buy_attempt+1}/3 failed: {e}")
                                    if buy_attempt < 2:
                                        await asyncio.sleep(60)  # wait 60s between buy attempts

                                if not bought_any:
                                    # All buy attempts failed — cooldown + clear blacklist + retry
                                    logger.warning(f"[Birth] Worker {worker_id}: auto-buy failed 3x, cooldown 2min then recycling proxies...")
                                    await asyncio.sleep(120)
                                    proxy_blacklist.clear()
                                continue
                            else:
                                logger.warning(f"[Birth] Worker {worker_id}: no free proxy, waiting 5s...")
                                await asyncio.sleep(5)
                                continue

                        # Increment per-provider usage counter
                        if proxy:
                            proxy_manager.increment_provider_usage(proxy, request.provider)

                        thread_log = ThreadLog(
                            task_id=task.id,
                            thread_index=name_index[0],
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

                        # SMS: chain handles provider rotation + country rules automatically
                        # No need for per-worker deepcopy — chain creates providers internally

                        account = None
                        if request.provider == "outlook":
                            account = await register_single_outlook(
                                browser_manager, proxy,
                                worker_name_pool, captcha, db, thread_log,
                                ACTIVE_PAGES=ACTIVE_PAGES,
                                BIRTH_CANCEL_EVENT=BIRTH_CANCEL_EVENT,
                            )
                        elif request.provider == "hotmail":
                            account = await register_single_outlook(
                                browser_manager, proxy,
                                worker_name_pool, captcha, db, thread_log,
                                domain="hotmail.com",
                                ACTIVE_PAGES=ACTIVE_PAGES,
                                BIRTH_CANCEL_EVENT=BIRTH_CANCEL_EVENT,
                            )
                        elif request.provider == "gmail":
                            if not has_sms_chain:
                                thread_log.status = "error"
                                thread_log.error_message = "Gmail requires SMS provider (configure 5SIM/Grizzly/SimSMS in Settings)"
                                db.commit()
                                return
                            account = await register_single_gmail(
                                browser_manager, proxy, worker_name_pool,
                                captcha, None, db, thread_log,
                                ACTIVE_PAGES=ACTIVE_PAGES,
                                BIRTH_CANCEL_EVENT=BIRTH_CANCEL_EVENT,
                            )
                        elif request.provider == "yahoo":
                            if not has_sms_chain:
                                thread_log.status = "error"
                                thread_log.error_message = "Yahoo requires SMS provider (configure 5SIM/Grizzly/SimSMS in Settings)"
                                db.commit()
                                return
                            account = await register_single_yahoo(
                                browser_manager, proxy,
                                worker_name_pool, captcha, None, db, thread_log,
                                ACTIVE_PAGES=ACTIVE_PAGES,
                                BIRTH_CANCEL_EVENT=BIRTH_CANCEL_EVENT,
                            )
                        elif request.provider == "aol":
                            if not has_sms_chain:
                                thread_log.status = "error"
                                thread_log.error_message = "AOL requires SMS provider (configure 5SIM/Grizzly/SimSMS in Settings)"
                                db.commit()
                                return
                            account = await register_single_aol(
                                browser_manager, proxy,
                                worker_name_pool, None, db, thread_log,
                                ACTIVE_PAGES=ACTIVE_PAGES,
                                BIRTH_CANCEL_EVENT=BIRTH_CANCEL_EVENT,
                            )
                        elif request.provider == "protonmail":
                            account = await register_single_protonmail(
                                browser_manager, proxy,
                                worker_name_pool, captcha, db, thread_log,
                                ACTIVE_PAGES=ACTIVE_PAGES,
                                BIRTH_CANCEL_EVENT=BIRTH_CANCEL_EVENT,
                            )
                        else:
                            thread_log.status = "error"
                            thread_log.error_message = f"Provider '{request.provider}' not supported"
                            db.commit()
                            return

                        if account:
                            # Bind proxy permanently to account
                            if proxy:
                                proxy_manager.bind_proxy_to_account(proxy, account)
                                proxies_in_use.discard(proxy.id)  # Bound to account — no longer in contention

                            farm.accounts.append(account)
                            thread_log.status = "done"
                            thread_log.account_email = account.email

                            async with job_lock:
                                registered_accounts.append(account)
                                success_counter[0] += 1
                                consecutive_failures[0] = 0  # reset on success
                                # Reset all resource exhaustion counters on success
                                sms_round_fails[0] = 0
                                captcha_round_fails[0] = 0
                                proxy_round_fails[0] = 0
                                task.completed_items = success_counter[0]

                            db.commit()
                            logger.info(f"[Birth] [OK] Worker {worker_id}: {account.email} "
                                        f"({success_counter[0]}/{request.quantity})")
                        else:
                            task.failed_items = (task.failed_items or 0) + 1
                            async with job_lock:
                                consecutive_failures[0] += 1
                            thread_log.status = "error"
                            if not thread_log.error_message:
                                thread_log.error_message = "Registration not completed"
                            thread_log.error_category = classify_error(thread_log.error_message)

                            # Smart retry: blacklist proxy if E500/IP/E302/E303 blocked
                            err_msg = (thread_log.error_message or "").lower()
                            if proxy and ("ip" in err_msg or "e500" in err_msg or "blocked" in err_msg
                                          or "e302" in err_msg or "e303" in err_msg
                                          or "something went wrong" in err_msg
                                          or "e501" in err_msg or "can't create" in err_msg
                                          or "unusual activity" in err_msg):
                                proxy_blacklist.add(proxy.id)
                                logger.info(f"[Birth] Proxy {proxy.host} blacklisted for this task (err: {err_msg[:80]})")
                                # Increment usage counter by 1 (NOT max out)
                                # Proxy survives multiple E500s before hitting limit
                                provider_lower = request.provider.lower()
                                attr = f"use_{provider_lower}"
                                if hasattr(proxy, attr):
                                    current = getattr(proxy, attr) or 0
                                    setattr(proxy, attr, current + 1)
                                    db.commit()
                                    logger.info(f"[Birth] Proxy {proxy.host}: {attr} incremented to {current + 1} (proxy error for {request.provider})")

                            # Smart retry: blacklist country if SMS actually timed out
                            # (NOT for "no numbers" or user cancel - only real delivery failure)
                            # Country blacklisting is now handled by SMS chain internally
                            # (get_next_sms_number tracks used_numbers and switches providers)

                            db.commit()
                            logger.info(f"[Birth] [FAIL] Worker {worker_id}: attempt {name_index[0]} failed, retrying...")

                            # ── Classify failure reason for resource exhaustion ──
                            err_msg = (thread_log.error_message or "").lower()
                            async with job_lock:
                                if any(x in err_msg for x in ["sms", "phone", "code not received", "no numbers", "verification code"]):
                                    sms_round_fails[0] += 1
                                    captcha_round_fails[0] = 0
                                    proxy_round_fails[0] = 0
                                    if sms_round_fails[0] >= SMS_MAX_ROUNDS:
                                        task.stop_reason = f"Process stopped — SMS exhausted ({SMS_MAX_ROUNDS} consecutive SMS failures, 2 full rounds through all providers)"
                                        return
                                elif any(x in err_msg for x in ["captcha", "recaptcha", "funcaptcha", "hcaptcha", "captcha_fail"]):
                                    captcha_round_fails[0] += 1
                                    sms_round_fails[0] = 0
                                    proxy_round_fails[0] = 0
                                    if captcha_round_fails[0] >= CAPTCHA_MAX_ROUNDS:
                                        task.stop_reason = f"Process stopped — CAPTCHA exhausted ({CAPTCHA_MAX_ROUNDS} consecutive failures, all captcha providers failed)"
                                        return
                                elif any(x in err_msg for x in ["e500", "ip", "blocked", "proxy", "datacenter", "asn",
                                                                 "e303", "something went wrong", "e501", "e304"]):
                                    proxy_round_fails[0] += 1
                                    sms_round_fails[0] = 0
                                    captcha_round_fails[0] = 0
                                    if proxy_round_fails[0] >= PROXY_MAX_ROUNDS:
                                        # NEVER STOP — auto-buy residential proxies and keep going
                                        logger.warning(f"[Birth] {PROXY_MAX_ROUNDS} proxy failures — auto-buying fresh residential proxies...")
                                        bought_any = False
                                        for buy_attempt in range(3):
                                            if task.id in BIRTH_CANCEL:
                                                return
                                            try:
                                                new_proxies = await asyncio.to_thread(
                                                    tiered_auto_buy,
                                                    provider=request.provider,
                                                    count=3,
                                                    country=auto_buy_geo,
                                                )
                                                if new_proxies:
                                                    for np in new_proxies:
                                                        p = Proxy(
                                                            host=np["host"], port=np["port"],
                                                            username=np.get("username", ""),
                                                            password=np.get("password", ""),
                                                            protocol=np.get("protocol", "http"),
                                                            proxy_type=np.get("proxy_type", "residential"),
                                                            geo=np.get("geo", "US"),
                                                            status=ProxyStatus.ACTIVE,
                                                            external_id=np.get("external_id", ""),
                                                            source=np.get("source", "auto-buy"),
                                                        )
                                                        db.add(p)
                                                        db.commit()
                                                        proxy_pool.append(p)
                                                    proxy_blacklist.clear()
                                                    proxy_round_fails[0] = 0
                                                    bought_any = True
                                                    logger.info(f"[Birth] Auto-bought {len(new_proxies)} residential proxies, continuing...")
                                                    break
                                            except Exception as buy_err:
                                                logger.warning(f"[Birth] Auto-buy attempt {buy_attempt+1}/3 failed: {buy_err}")
                                            if buy_attempt < 2:
                                                await asyncio.sleep(60)
                                        if not bought_any:
                                            # Failed to buy — cooldown + clear blacklist + keep trying
                                            logger.warning(f"[Birth] Auto-buy failed 3x, cooldown 2min then recycling all proxies...")
                                            await asyncio.sleep(120)
                                            proxy_blacklist.clear()
                                            proxy_round_fails[0] = 0
                                        # NEVER return — continue the loop
                                else:
                                    # Unknown error — don't reset resource counters
                                    pass

                            await asyncio.sleep(random.uniform(2, 5))

                    except Exception as e:
                        err_str = str(e)
                        err_lower = err_str.lower()
                        is_browser_crash = any(x in err_lower for x in [
                            "connection closed", "browser has been closed", "target closed",
                            "target page", "context or browser", "reading from the driver",
                        ])
                        if is_browser_crash:
                            logger.warning(f"[Birth] Worker {worker_id}: browser crashed, will auto-restart on next attempt: {err_str[:200]}")
                        else:
                            logger.error(f"[Birth] Worker {worker_id} crashed: {e}", exc_info=True)
                        try:
                            task.failed_items = (task.failed_items or 0) + 1
                            async with job_lock:
                                consecutive_failures[0] += 1
                            if thread_log:
                                thread_log.status = "error"
                                thread_log.error_message = f"{'[RETRY] Browser crash' if is_browser_crash else 'Crash'}: {err_str[:400]}"
                                thread_log.error_category = classify_error(thread_log.error_message)
                            db.commit()
                        except Exception:
                            pass
                        # Wait longer on browser crash to give auto-restart time
                        await asyncio.sleep(5 if is_browser_crash else 3)
                    finally:
                        # ALWAYS release proxy from in-use tracking — covers ALL exit paths
                        # (success, failure, exception, early return on resource exhaustion)
                        if proxy and hasattr(proxy, 'id'):
                            proxies_in_use.discard(proxy.id)

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
                task.stop_reason = f"Process stopped - registered {success_counter[0]} of {request.quantity} (rest - errors)"
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
                task.stop_reason = f"Process stopped - critical error: {str(e)[:200]}"
                task.completed_at = datetime.utcnow()
                db.commit()
            except Exception:
                pass
    finally:
        engine_manager.finish_engine(EngineType.AUTOREG)
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
    "ru": ("Russia", ""), "ua": ("Ukraine", ""), "kz": ("Kazakhstan", ""),
    "cn": ("China", ""), "ph": ("Philippines", ""), "id": ("Indonesia", ""),
    "ke": ("Kenya", ""), "br": ("Brazil", ""), "us": ("USA", ""),
    "il": ("Israel", ""), "pl": ("Poland", ""), "uk": ("UK", ""),
    "us_v": ("USA Virtual", ""), "ng": ("Nigeria", ""), "eg": ("Egypt", ""),
    "fr": ("France", ""), "ie": ("Ireland", ""), "za": ("South Africa", ""),
    "ro": ("Romania", ""), "se": ("Sweden", ""), "ee": ("Estonia", ""),
    "ca": ("Canada", ""), "de": ("Germany", ""), "nl": ("Netherlands", ""),
    "at": ("Austria", ""), "th": ("Thailand", ""), "mx": ("Mexico", ""),
    "es": ("Spain", ""), "tr": ("Turkey", ""), "cz": ("Czechia", ""),
    "pe": ("Peru", ""), "nz": ("New Zealand", ""),
}


@router.get("/sms-countries")
async def get_sms_countries():
    """Return available SMS countries from SimSMS."""
    from backend.services.simsms_provider import COUNTRY_CODES
    countries = []
    for code in COUNTRY_CODES:
        name, flag = SMS_COUNTRY_NAMES.get(code, (code, ""))
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
        # Extract provider from task details
        task_provider = None
        if running_task.details:
            # details format: "Registering N provider accounts"
            parts = (running_task.details or "").split()
            for p in ['outlook', 'gmail', 'yahoo', 'aol', 'hotmail', 'protonmail']:
                if p in running_task.details.lower():
                    task_provider = p
                    break

        # Error breakdown
        error_breakdown = {"proxy": 0, "captcha": 0, "sms": 0, "block": 0,
                           "page": 0, "browser": 0, "unknown": 0}
        err_logs = db.query(ThreadLog).filter(
            ThreadLog.task_id == running_task.id,
            ThreadLog.status == "error",
        ).all()
        for el in err_logs:
            cat = el.error_category or classify_error(el.error_message)
            if cat in error_breakdown:
                error_breakdown[cat] += 1
            else:
                error_breakdown["unknown"] += 1

        total_attempts = (running_task.completed_items or 0) + (running_task.failed_items or 0)
        success_rate = round((running_task.completed_items or 0) / total_attempts * 100) if total_attempts > 0 else 0

        return {
            "running": True,
            "task_id": running_task.id,
            "total": running_task.total_items or 0,
            "completed": running_task.completed_items or 0,
            "failed": running_task.failed_items or 0,
            "status": "running",
            "stop_reason": running_task.stop_reason,
            "provider": task_provider,
            "success_rate": success_rate,
            "error_breakdown": error_breakdown,
        }

    # Check last finished task
    last_task = db.query(Task).filter(
        Task.type == "birth",
    ).order_by(Task.created_at.desc()).first()

    if last_task:
        task_provider = None
        if last_task.details:
            for p in ['outlook', 'gmail', 'yahoo', 'aol', 'hotmail', 'protonmail']:
                if p in last_task.details.lower():
                    task_provider = p
                    break

        # Error breakdown for finished task
        error_breakdown = {"proxy": 0, "captcha": 0, "sms": 0, "block": 0,
                           "page": 0, "browser": 0, "unknown": 0}
        err_logs = db.query(ThreadLog).filter(
            ThreadLog.task_id == last_task.id,
            ThreadLog.status == "error",
        ).all()
        for el in err_logs:
            cat = el.error_category or classify_error(el.error_message)
            if cat in error_breakdown:
                error_breakdown[cat] += 1
            else:
                error_breakdown["unknown"] += 1

        total_attempts = (last_task.completed_items or 0) + (last_task.failed_items or 0)
        success_rate = round((last_task.completed_items or 0) / total_attempts * 100) if total_attempts > 0 else 0

        return {
            "running": False,
            "task_id": last_task.id,
            "total": last_task.total_items or 0,
            "completed": last_task.completed_items or 0,
            "failed": last_task.failed_items or 0,
            "status": last_task.status,
            "stop_reason": last_task.stop_reason,
            "error": last_task.details if last_task.status == "failed" else None,
            "provider": task_provider,
            "success_rate": success_rate,
            "error_breakdown": error_breakdown,
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
            t.details = "Stopped by user (instant)"
            t.stop_reason = "Stopped by user"
        else:
            t.details = "Stopping: waiting for threads to finish..."
            t.stop_reason = "Stopped by user (waiting for threads)"
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
            tl.current_action = "Stopped"

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
        return {"error": "Thread not found or browser closed", "active_threads": list(ACTIVE_PAGES.keys())}
    try:
        page = entry["page"]
        screenshot_bytes = await page.screenshot(type="png")
        return Response(content=screenshot_bytes, media_type="image/png")
    except Exception as e:
        return {"error": f"Screenshot failed: {str(e)[:200]}"}


@router.get("/active-pages")
async def get_active_pages():
    """List all thread IDs with active browser pages."""
    return {"active": list(ACTIVE_PAGES.keys())}

