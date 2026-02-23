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


def _get_sms_provider(provider_name: str):
    """Get configured SMS provider."""
    config = load_config()
    if provider_name == "grizzly":
        key = config.get("sms", {}).get("grizzly", {}).get("api_key", "")
        return GrizzlySMS(key) if key else None
    else:
        key = config.get("sms", {}).get("simsms", {}).get("api_key", "")
        return SimSmsProvider(key) if key else None


def _get_captcha_provider():
    key = get_api_key("capguru") or ""
    return CaptchaProvider(api_key=key) if key else None


DEBUG_SCREENSHOT_DIR = str(Path(__file__).resolve().parent.parent.parent / "user_data" / "debug_screenshots")


async def _debug_screenshot(page, label: str, _log=None):
    """Capture a debug screenshot at a key flow point. Never crashes."""
    try:
        Path(DEBUG_SCREENSHOT_DIR).mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%H%M%S")
        fname = f"{ts}_{label}.png"
        path = str(Path(DEBUG_SCREENSHOT_DIR) / fname)
        await page.screenshot(path=path, full_page=False)
        if _log:
            _log(f"📸 Скриншот: {fname}")
        return path
    except Exception as e:
        if _log:
            _log(f"📸 Скриншот не удался: {e}")
        return None


async def _human_delay(min_s=0.5, max_s=2.0):
    """Random human-like delay."""
    await asyncio.sleep(random.uniform(min_s, max_s))


async def _human_mouse_to(page, selector):
    """Move mouse to element center with random offset, simulating real user."""
    try:
        el = page.locator(selector).first
        box = await el.bounding_box()
        if box:
            # Random offset within element (not perfectly centered)
            x = box['x'] + box['width'] * random.uniform(0.25, 0.75)
            y = box['y'] + box['height'] * random.uniform(0.25, 0.75)
            await page.mouse.move(x, y, steps=random.randint(5, 15))
            await _human_delay(0.1, 0.3)
    except Exception:
        pass


async def _human_click(page, selector):
    """Move mouse to element, then click with human-like timing."""
    await _human_mouse_to(page, selector)
    try:
        await page.locator(selector).first.click()
    except Exception:
        pass
    await _human_delay(0.2, 0.5)


async def _human_fill(page, selector, text):
    """Clear field, then type text character-by-character with realistic speed.
    Includes micro-pauses, speed variations, and occasional corrections."""
    try:
        el = page.locator(selector).first
        await _human_mouse_to(page, selector)
        await el.click()
        await _human_delay(0.2, 0.5)
        # Clear any existing text
        await el.fill("")
        await _human_delay(0.1, 0.3)
        # Type each character with varying speed
        for i, char in enumerate(text):
            delay_ms = random.randint(50, 170)
            # Occasionally type slower (thinking pause)
            if random.random() < 0.08:
                delay_ms = random.randint(200, 500)
            await page.keyboard.type(char, delay=delay_ms)
            # Micro-pause every 3-7 chars
            if i > 0 and i % random.randint(3, 7) == 0 and random.random() < 0.3:
                await _human_delay(0.15, 0.4)
    except Exception:
        # Fallback: just fill directly
        try:
            await page.locator(selector).first.fill(text)
        except Exception:
            pass


async def _human_type(page, selector, text, thread_log=None, db=None):
    """Type text with human-like delays and occasional pauses."""
    el = page.locator(selector)
    await el.click()
    await _human_delay(0.3, 0.8)
    for char in text:
        await el.type(char, delay=random.randint(45, 120))
        # Random micro-pause every 3-6 chars
        if random.random() < 0.15:
            await _human_delay(0.2, 0.6)


async def _check_error_on_page(page) -> str | None:
    """Check if Microsoft shows an error message."""
    error_selectors = [
        '#MemberNameError',
        '#PasswordError',
        '#FirstNameError',
        '#LastNameError',
        '#BirthDateError',
        '.alert-error',
        '#error',
        '#ServerError',
    ]
    for sel in error_selectors:
        el = page.locator(sel)
        if await el.count() > 0:
            text = await el.text_content()
            if text and text.strip():
                return text.strip()
    return None


async def _fluent_combobox_select(page, button_selectors: list[str], value: str, label: str, _log, timeout=5000):
    """Select a value from a Fluent UI combobox (button[role=combobox] + div[role=listbox]).
    
    MS signup uses Fluent UI — dropdowns are buttons that open a listbox of div[role=option] items.
    """
    # Find the combobox button
    btn = None
    for sel in button_selectors:
        try:
            if await page.locator(sel).count() > 0:
                btn = sel
                break
        except Exception:
            continue
    
    if not btn:
        _log(f"⚠️ Fluent combobox '{label}' не найден")
        return False
    
    # Click the button to open the listbox
    try:
        await page.locator(btn).first.click()
        await _human_delay(0.3, 0.6)
    except Exception as e:
        _log(f"⚠️ Не удалось кликнуть combobox '{label}': {e}")
        return False
    
    # Wait for listbox to appear
    try:
        await page.wait_for_selector('[role="listbox"]', timeout=3000)
    except Exception:
        _log(f"⚠️ Listbox для '{label}' не появился")
        return False
    
    # Find and click the right option
    # Options are div[role="option"] inside the listbox
    options = page.locator('[role="listbox"] [role="option"]')
    count = await options.count()
    
    for i in range(count):
        try:
            text = (await options.nth(i).inner_text()).strip()
            # Match by exact text, or starts with the value
            if text == value or text.startswith(value):
                await options.nth(i).click()
                _log(f"✅ {label}: выбрано '{text}'")
                await _human_delay(0.2, 0.4)
                return True
        except Exception:
            continue
    
    # Fallback: try clicking by index (value is 1-based for months)
    try:
        idx = int(value) - 1  # Convert 1-based to 0-based
        if 0 <= idx < count:
            text = (await options.nth(idx).inner_text()).strip()
            await options.nth(idx).click()
            _log(f"✅ {label}: выбрано по индексу '{text}'")
            await _human_delay(0.2, 0.4)
            return True
    except (ValueError, Exception):
        pass
    
    _log(f"⚠️ Не удалось выбрать '{value}' в combobox '{label}' (найдено {count} опций)")
    # Close the listbox by pressing Escape
    try:
        await page.keyboard.press("Escape")
    except Exception:
        pass
    return False

async def _wait_for_any(page, selectors: list[str], timeout: int = 20000) -> str | None:
    """Wait for any of the given selectors to appear. Returns which one appeared."""
    # Quick scan first (already visible?)
    for sel in selectors:
        try:
            if await page.locator(sel).count() > 0:
                vis = await page.locator(sel).first.is_visible()
                if vis:
                    return sel
        except Exception:
            pass

    # Slow scan with timeout
    per_sel_timeout = max(2000, timeout // len(selectors))
    for sel in selectors:
        try:
            await page.wait_for_selector(sel, timeout=per_sel_timeout, state="visible")
            if await page.locator(sel).count() > 0:
                return sel
        except Exception:
            pass
    return None


async def _step_screenshot(page, step_name: str, username: str = "unknown"):
    """Save a debug screenshot for a registration step."""
    import os
    try:
        os.makedirs("user_data/screenshots", exist_ok=True)
        ts = datetime.utcnow().strftime("%H%M%S")
        path = f"user_data/screenshots/{username}_{step_name}_{ts}.png"
        await page.screenshot(path=path)
        return path
    except Exception:
        return None


async def _wait_and_find(page, selectors: list[str], step_name: str, 
                         username: str, _log_fn=None, _err_fn=None,
                         timeout: int = 25000, required: bool = True):
    """
    Wait for any selector, screenshot on failure.
    Returns found selector or None. If required=True and not found, logs error.
    """
    found = await _wait_for_any(page, selectors, timeout=timeout)
    if not found and required:
        ss = await _step_screenshot(page, f"FAIL_{step_name}", username)
        msg = f"Не найдено поле '{step_name}'. URL: {page.url}"
        if ss and _log_fn:
            _log_fn(f"📸 Скриншот: {ss}")
        if _err_fn:
            _err_fn(msg)
        else:
            logger.error(f"[Birth] {msg}")
    return found


async def _detect_and_solve_recaptcha(page, captcha_provider, log_fn=None):
    """
    Universal reCAPTCHA detector + solver.
    Checks if a reCAPTCHA iframe is present, extracts sitekey, solves via CapGuru.
    Returns True if captcha was solved, False if no captcha found.
    """
    if not captcha_provider or not captcha_provider.api_key:
        return False

    def _log(msg):
        if log_fn:
            log_fn(msg)
        else:
            logger.info(f"[Captcha] {msg}")

    try:
        # Check for reCAPTCHA iframe
        recaptcha_iframe = page.locator('iframe[src*="recaptcha"], iframe[src*="google.com/recaptcha"]')
        captcha_count = await recaptcha_iframe.count()

        if captcha_count == 0:
            # Also check for invisible reCAPTCHA via g-recaptcha div
            grecaptcha = page.locator('.g-recaptcha, [data-sitekey]')
            captcha_count = await grecaptcha.count()

        if captcha_count == 0:
            return False

        _log("🔐 reCAPTCHA обнаружена! Решаем...")

        # Extract sitekey
        sitekey = None
        try:
            # Try from data-sitekey attribute
            el = page.locator('[data-sitekey]').first
            if await el.count() > 0:
                sitekey = await el.get_attribute('data-sitekey')
        except Exception:
            pass

        if not sitekey:
            try:
                # Try from iframe src
                iframe = page.locator('iframe[src*="recaptcha"]').first
                src = await iframe.get_attribute('src') or ""
                if "k=" in src:
                    sitekey = src.split("k=")[1].split("&")[0]
            except Exception:
                pass

        if not sitekey:
            _log("Sitekey не найден")
            return False

        _log(f"Sitekey: {sitekey[:20]}...")

        # Solve via CapGuru
        page_url = page.url
        token = await asyncio.to_thread(
            captcha_provider.solve_captcha, page_url, sitekey
        )

        if not token:
            _log("❌ Не удалось решить CAPTCHA")
            return False

        _log("✅ CAPTCHA решена! Вставляем токен...")

        # Inject token into the page
        await page.evaluate(f"""
            (function() {{
                // Set g-recaptcha-response textarea
                var textareas = document.querySelectorAll('[id*="g-recaptcha-response"], textarea[name="g-recaptcha-response"]');
                for (var i = 0; i < textareas.length; i++) {{
                    textareas[i].innerHTML = '{token}';
                    textareas[i].value = '{token}';
                    textareas[i].style.display = 'block';
                }}
                // Try callback
                if (typeof ___grecaptcha_cfg !== 'undefined') {{
                    var keys = Object.keys(___grecaptcha_cfg.clients);
                    for (var k = 0; k < keys.length; k++) {{
                        try {{
                            var client = ___grecaptcha_cfg.clients[keys[k]];
                            var callback = client && client.rr && client.rr.callback;
                            if (callback) callback('{token}');
                        }} catch(e) {{}}
                    }}
                }}
                // grecaptcha.enterprise callback
                if (typeof grecaptcha !== 'undefined' && grecaptcha.enterprise) {{
                    try {{ grecaptcha.enterprise.execute(); }} catch(e) {{}}
                }}
            }})();
        """)

        await _human_delay(1, 2)
        return True

    except Exception as e:
        logger.debug(f"Captcha detection error: {e}")
        return False


async def register_single_outlook(
    browser_manager: BrowserManager,
    proxy: Proxy | None,
    device_type: str,
    name_pool: list,
    captcha_provider: CaptchaProvider | None,
    db: Session,
    thread_log: ThreadLog | None = None,
    domain: str = "outlook.com",
) -> Account | None:
    """Register a single Outlook/Hotmail account with human-like behavior."""
    if not name_pool:
        logger.error("[Birth] ❌ Нет имён! Загрузите пакет имён перед регистрацией.")
        if thread_log:
            thread_log.status = "error"
            thread_log.error_message = "Нет имён! Загрузите пакет имён."
            try: db.commit()
            except: pass
        return None
    first_name, last_name = random.choice(name_pool)
    password = generate_password()
    birthday = generate_birthday()
    username = generate_username(first_name, last_name)
    email = f"{username}@{domain}"
    provider_name = "hotmail" if "hotmail" in domain else "outlook"

    context = await browser_manager.create_context(
        proxy=proxy,
        device_type=device_type,
        geo=None,
    )

    def _log(msg: str):
        wid = getattr(thread_log, '_worker_id', '?') if thread_log else '?'
        logger.info(f"[Outlook][W{wid}] {msg}")
        if thread_log:
            thread_log.current_action = f"[W{wid}] {msg}"
            try:
                db.commit()
            except Exception:
                pass

    def _err(msg: str):
        wid = getattr(thread_log, '_worker_id', '?') if thread_log else '?'
        logger.error(f"[Outlook][W{wid}] {msg}")
        if thread_log:
            thread_log.error_message = f"[W{wid}] {msg}"[:500]
            try:
                db.commit()
            except Exception:
                pass

    try:
        page = await context.new_page()

        # Register in ACTIVE_PAGES for screenshot/control access
        thread_id = thread_log.id if thread_log else 0
        ACTIVE_PAGES[thread_id] = {"page": page, "context": context}

        # Pre-registration warmup — look like a real person
        _log("Прогрев сессии...")
        try:
            await pre_registration_warmup(page)
        except Exception as warmup_e:
            logger.debug(f"Warmup error (proxy may be dead): {warmup_e}")

        # Check if warmup result indicates dead proxy
        warmup_url = page.url or ""
        if "chrome-error" in warmup_url or "about:blank" == warmup_url:
            _log("⚠️ Прокси не работает, прогрев не удался")

        # Step 1: Navigate — Outlook redirects, so wait for networkidle
        _log("Открытие страницы регистрации...")
        try:
            await page.goto(
                "https://signup.live.com/signup",
                wait_until="networkidle",
                timeout=60000,
            )
        except Exception as nav_e:
            logger.warning(f"[Birth] Navigation error: {nav_e}")

        await _human_delay(2, 4)

        # CRITICAL: Check if proxy is dead (ERR_TUNNEL_CONNECTION_FAILED)
        current_url = page.url or ""
        if "chrome-error" in current_url or "about:blank" == current_url:
            _err(f"🔴 Прокси МЁРТВ — страница не загрузилась (URL: {current_url})")
            # Mark proxy as dead in DB
            if proxy:
                try:
                    proxy.status = ProxyStatus.DEAD
                    proxy.fail_count = (proxy.fail_count or 0) + 1
                    db.commit()
                    logger.warning(f"Proxy marked DEAD during birth: {proxy.host}:{proxy.port}")
                except Exception:
                    pass
            return None

        await random_mouse_move(page, steps=3)
        _log(f"Страница: {page.url}")

        # Modern Outlook signup: click "Get a new email address" link first
        new_email_link = page.locator('a#liveSwitch, a[id*="Switch"], a:has-text("new email"), a:has-text("новый"), a:has-text("Get a new")')
        got_new_email_mode = False
        try:
            if await new_email_link.count() > 0:
                _log("Нажимаю 'Получить новый email'...")
                await new_email_link.first.click()
                await _human_delay(1.5, 3)
                got_new_email_mode = True
        except Exception:
            pass

        # Check if domain dropdown appeared (= username-only mode)
        if got_new_email_mode:
            domain_dropdown = await _wait_for_any(page, [
                'select#LiveDomainBoxList', '#LiveDomainBoxList',
                'select[name="DomainList"]',
            ], timeout=3000)
            if domain_dropdown:
                got_new_email_mode = True
                _log("Режим username-only (dropdown домена виден)")
            else:
                got_new_email_mode = False
                _log("Dropdown домена не виден, используем полный email")

        # EMAIL FIELD — wide fallback selectors (includes old MemberName + new Fluent UI Email)
        email_selectors = [
            'input[name="MemberName"]', '#MemberName', '#iMemberName',
            'input[name="Email"]',  # New Fluent UI flow
            'input[type="email"]', 'input[type="text"][name="MemberName"]',
            'input[aria-label*="email"]', 'input[aria-label*="Email"]',
            'input[placeholder*="email"]', 'input[placeholder*="Email"]',
            'input[id*="floatingLabel"]',  # Fluent UI dynamic IDs
        ]
        _log(f"Ввод email: {email}")
        found = await _wait_and_find(page, email_selectors, "email", username, _log, _err, timeout=20000)
        if not found:
            return None

        # Decide what to type: username-only or full email
        text_to_enter = username if got_new_email_mode else email
        _log(f"Вводим: {text_to_enter}")

        await page.locator(found).first.click()
        await _human_delay(0.3, 0.8)
        await page.locator(found).first.fill("")
        for char in text_to_enter:
            await page.locator(found).first.type(char, delay=random.randint(50, 110))
            if random.random() < 0.12:
                await _human_delay(0.2, 0.5)
        await _human_delay(0.8, 1.5)

        # Select domain from dropdown if in username-only mode
        if got_new_email_mode and domain != "outlook.com":
            domain_sel = await _wait_for_any(page, [
                'select#LiveDomainBoxList', '#LiveDomainBoxList',
                'select[name="DomainList"]', 'select[aria-label*="domain"]',
            ], timeout=5000)
            if domain_sel:
                _log(f"Выбор домена: @{domain}")
                await page.locator(domain_sel).first.select_option(domain)
                await _human_delay(0.5, 1)

        # Click Next button
        next_selectors = ['#iSignupAction', 'input[type="submit"]', 'button[type="submit"]']
        next_btn = await _wait_for_any(page, next_selectors, timeout=5000)
        if next_btn:
            await page.locator(next_btn).first.click()
        else:
            await page.keyboard.press("Enter")

        # Wait for page to transition (URL changes or new field appears)
        await _human_delay(3, 6)

        # Check for email-taken error
        err_text = await _check_error_on_page(page)
        if err_text:
            logger.warning(f"[Birth] Email error (retrying): {err_text}")
            username = generate_username(first_name, last_name)
            email = f"{username}@outlook.com"
            found2 = await _wait_for_any(page, email_selectors, timeout=5000)
            if found2:
                await page.locator(found2).first.fill(username)
            await _human_delay(0.5, 1)
            if next_btn:
                await page.locator(next_btn).first.click()
            else:
                await page.keyboard.press("Enter")
            await _human_delay(3, 5)

        # PASSWORD FIELD — wait for page transition after email
        _log("Ввод пароля...")
        pwd_selectors = [
            'input[name="Password"]', '#PasswordInput', 'input[type="password"]',
            '#iPasswordInput', 'input[name="passwd"]', '#Password',
            'input[aria-label*="assword"]', 'input[aria-label*="арол"]',
            'input[data-purpose*="assword"]', 'input[placeholder*="assword"]',
            'input[placeholder*="арол"]',
        ]
        found = await _wait_and_find(page, pwd_selectors, "password", username, _log, _err, timeout=25000)
        if not found:
            return None

        await page.locator(found).first.click()
        await _human_delay(0.3, 0.6)
        for char in password:
            await page.locator(found).first.type(char, delay=random.randint(40, 90))
            if random.random() < 0.10:
                await _human_delay(0.15, 0.4)
        await _human_delay(0.5, 1.2)

        next_btn2 = await _wait_for_any(page, next_selectors, timeout=3000)
        if next_btn2:
            await page.locator(next_btn2).first.click()
        else:
            await page.keyboard.press("Enter")
        await _human_delay(2, 4)

        # ═══════════════════════════════════════════════════════════
        # NEW MS FLOW (2025): Password → Birthday → Name → CAPTCHA
        # ═══════════════════════════════════════════════════════════

        # BIRTHDAY / "Add some details" page (Fluent UI)
        _log("Ввод даты рождения...")
        await _human_delay(1, 2)
        await _step_screenshot(page, "before_birthday", username)

        # ── MONTH LIST (English names for matching) ──
        month_names = [
            "", "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        month_name = month_names[birthday.month] if 1 <= birthday.month <= 12 else str(birthday.month)

        # ── COUNTRY (Fluent UI combobox button) — random country ──
        country_pool = [
            "United States", "United Kingdom", "Canada", "Australia",
            "Germany", "France", "Netherlands", "Sweden", "Ireland",
            "New Zealand", "Switzerland", "Austria", "Denmark", "Norway",
        ]
        chosen_country = random.choice(country_pool)
        _log(f"Выбор страны: {chosen_country}")
        country_ok = await _fluent_combobox_select(page, [
            '#countryDropdownId',
            'button[name="countryDropdownName"]',
            'button[aria-label*="ountry"]',
            'button[aria-label*="тран"]',
            'button[role="combobox"]:first-of-type',
        ], chosen_country, "Country", _log, timeout=5000)
        if not country_ok:
            # Try native select fallback (old flow)
            old_country = await _wait_for_any(page, [
                'select[id*="Country"]', 'select[name*="Country"]',
            ], timeout=2000)
            if old_country:
                try:
                    await page.locator(old_country).first.select_option("US")
                    _log("Country: выбрано через native select")
                except Exception:
                    pass
        await _human_delay(0.5, 1.0)

        # ── BIRTH MONTH (Fluent UI combobox) ──
        month_ok = await _fluent_combobox_select(page, [
            '#BirthMonthDropdown',
            'button[name="BirthMonth"]',
            'button[aria-label*="irth month"]',
            'button[aria-label*="есяц"]',
        ], month_name, "Month", _log, timeout=10000)
        if not month_ok:
            # Native select fallback
            old_month = await _wait_for_any(page, [
                '#BirthMonth', 'select[name="BirthMonth"]',
            ], timeout=2000)
            if old_month:
                try:
                    await page.locator(old_month).first.select_option(str(birthday.month))
                    _log(f"Month: native select ({birthday.month})")
                    month_ok = True
                except Exception:
                    pass
        if not month_ok:
            _err(f"Не удалось выбрать месяц. URL: {page.url}")
            return None
        await _human_delay(0.3, 0.8)

        # ── BIRTH DAY (Fluent UI combobox) ──
        day_ok = await _fluent_combobox_select(page, [
            '#BirthDayDropdown',
            'button[name="BirthDay"]',
            'button[aria-label*="irth day"]',
            'button[aria-label*="ень рожд"]',
        ], str(birthday.day), "Day", _log, timeout=5000)
        if not day_ok:
            old_day = await _wait_for_any(page, [
                '#BirthDay', 'select[name="BirthDay"]',
            ], timeout=2000)
            if old_day:
                try:
                    await page.locator(old_day).first.select_option(str(birthday.day))
                    _log(f"Day: native select ({birthday.day})")
                except Exception:
                    pass
        await _human_delay(0.3, 0.8)

        # ── BIRTH YEAR (input field) ──
        year_sels = [
            'input[name="BirthYear"]', '#BirthYear',
            'input[aria-label*="irth year"]', 'input[aria-label*="од рожд"]',
            'input[type="number"]',
        ]
        year_sel = await _wait_for_any(page, year_sels, timeout=5000)
        if year_sel:
            await page.locator(year_sel).first.fill(str(birthday.year))
            _log(f"Year: {birthday.year}")
        else:
            _log("⚠️ Year field не найден")
        await _human_delay(0.5, 1)

        # Click Next after birthday
        next_btn_bday = await _wait_for_any(page, next_selectors, timeout=3000)
        if next_btn_bday:
            await page.locator(next_btn_bday).first.click()
        else:
            await page.keyboard.press("Enter")
        await _human_delay(2, 4)

        # ═══════════════════════════════════════════════════════════
        # NAME PAGE — "Add your name" (comes AFTER birthday in new flow)
        # ═══════════════════════════════════════════════════════════
        _log(f"Ввод имени: {first_name} {last_name}")
        fn_selectors = [
            '#firstNameInput',  # New Fluent UI
            'input[name="FirstName"]', '#FirstName', '#iFirstName',
            'input[name="DisplayName"]', '#DisplayName',
            'input[placeholder*="имя"]', 'input[placeholder*="irst"]',
            'input[aria-label*="irst name"]', 'input[aria-label*="имя"]',
        ]
        name_found = await _wait_for_any(page, fn_selectors, timeout=8000)
        if name_found:
            _log("Обнаружена страница имени")
            await page.locator(name_found).first.fill(first_name)
            await _human_delay(0.3, 0.8)

            ln_selectors = [
                '#lastNameInput',  # New Fluent UI
                'input[name="LastName"]', '#LastName', '#iLastName',
                'input[placeholder*="фамил"]', 'input[placeholder*="ast"]',
                'input[aria-label*="ast name"]', 'input[aria-label*="фам"]',
            ]
            found_ln = await _wait_for_any(page, ln_selectors, timeout=5000)
            if found_ln:
                await page.locator(found_ln).first.fill(last_name)
            await _human_delay(0.5, 1)

            next_btn_name = await _wait_for_any(page, next_selectors, timeout=3000)
            if next_btn_name:
                await page.locator(next_btn_name).first.click()
            else:
                await page.keyboard.press("Enter")
            await _human_delay(3, 6)
        else:
            _log("⚠️ Страница имени не найдена — возможно уже на CAPTCHA")

        # CAPTCHA — Arkose Labs (hsprotect.net) / FunCaptcha
        _log("Проверка CAPTCHA...")
        captcha_frame = page.locator('iframe[title*="captcha"], iframe[title*="Verification"], iframe[title*="Human"], iframe[src*="funcaptcha"], iframe[src*="hsprotect"], #enforcementFrame')
        if await captcha_frame.count() > 0:
            # FunCaptcha requires 2Captcha (CapGuru doesn't support it)
            from ..services.captcha_provider import get_twocaptcha_provider
            tc_provider = get_twocaptcha_provider()
            if tc_provider:
                _log("🔐 FunCaptcha обнаружена! Решаем через 2Captcha...")
                try:
                    # Outlook FunCaptcha public key
                    site_key = "B7D8911C-5CC8-A9A3-35B0-554ACEE604DA"
                    surl = "https://client-api.arkoselabs.com"
                    token = await asyncio.wait_for(
                        asyncio.to_thread(tc_provider.solve_funcaptcha, site_key, page.url, surl),
                        timeout=180,
                    )
                    if token:
                        _log("✅ FunCaptcha решена! Вставляем токен...")
                        # Inject token via multiple methods
                        await page.evaluate(f"""(() => {{
                            // Method 1: postMessage to enforcement frame
                            try {{
                                var ef = document.getElementById("enforcementFrame");
                                if (ef && ef.contentWindow) {{
                                    ef.contentWindow.postMessage(JSON.stringify({{token: "{token}"}}), "*");
                                }}
                            }} catch(e) {{}}
                            // Method 2: Set hidden input
                            try {{
                                var inputs = document.querySelectorAll('input[name*="fc-token"], input[name*="verification"]');
                                inputs.forEach(i => {{ i.value = "{token}"; }});
                            }} catch(e) {{}}
                            // Method 3: window.funcaptchaCallback
                            try {{ if (window.funcaptchaCallback) window.funcaptchaCallback("{token}"); }} catch(e) {{}}
                        }})()""")
                        await _human_delay(3, 6)
                        _log("Токен вставлен, ожидание...")
                    else:
                        _err("❌ 2Captcha не смог решить FunCaptcha")
                        return None
                except asyncio.TimeoutError:
                    _err("❌ Таймаут решения FunCaptcha (180с)")
                    return None
                except Exception as e:
                    _err(f"CAPTCHA ошибка: {str(e)[:200]}")
                    return None
            else:
                _err("FunCaptcha нужна, но ключ 2Captcha не настроен! Outlook требует 2Captcha для FunCaptcha.")
                return None

        # Verify success
        _log("Проверка результата...")
        await _human_delay(3, 5)
        final_url = page.url.lower()
        _log(f"Финальный URL: {final_url}")

        # Save session
        try:
            session_path = await browser_manager.save_session(context, 0)
        except Exception as se:
            logger.warning(f"[Birth] Session save warning: {se}")
            session_path = None

        # Create account record
        account = Account(
            email=email,
            password=password,
            provider=provider_name,
            first_name=first_name,
            last_name=last_name,
            gender="random",
            birthday=birthday,
            birth_ip=f"{proxy.host}" if proxy else None,
            status="new",
        )
        db.add(account)
        db.commit()
        db.refresh(account)

        # Save session with real account ID
        if session_path:
            try:
                account.browser_profile_path = await browser_manager.save_session(context, account.id)
                db.commit()
            except Exception:
                pass

        logger.info(f"✅ Registered: {email}")
        return account

    except Exception as e:
        logger.error(f"❌ Registration failed: {e}", exc_info=True)
        _err(str(e)[:500])
        return None
    finally:
        # Remove from active pages registry
        ACTIVE_PAGES.pop(thread_id, None)
        try:
            await context.close()
        except Exception:
            pass


async def register_single_gmail(
    browser_manager: BrowserManager,
    proxy: Proxy | None,
    name_pool: list,
    captcha_provider: CaptchaProvider | None,
    sms_provider,  # SimSmsProvider or GrizzlySMS
    db: Session,
    thread_log: ThreadLog | None = None,
) -> Account | None:
    """Register a single Gmail account on MOBILE device. Requires SMS."""
    if not name_pool:
        logger.error("[Gmail] ❌ Нет имён! Загрузите пакет имён перед регистрацией.")
        if thread_log:
            thread_log.status = "error"
            thread_log.error_message = "Нет имён! Загрузите пакет имён."
            try: db.commit()
            except: pass
        return None
    first_name, last_name = random.choice(name_pool)
    password = generate_password()
    username = generate_username(first_name, last_name)

    # Gmail = always mobile
    context = await browser_manager.create_context(
        proxy=proxy,
        device_type="phone_android",
        geo=None,
    )

    def _log(msg: str):
        wid = getattr(thread_log, '_worker_id', '?') if thread_log else '?'
        logger.info(f"[Gmail][W{wid}] {msg}")
        if thread_log:
            thread_log.current_action = f"[W{wid}] {msg}"
            try:
                db.commit()
            except Exception:
                pass

    def _err(msg: str):
        wid = getattr(thread_log, '_worker_id', '?') if thread_log else '?'
        logger.error(f"[Gmail][W{wid}] {msg}")
        if thread_log:
            thread_log.error_message = f"[W{wid}] {msg}"[:500]
            try:
                db.commit()
            except Exception:
                pass

    try:
        page = await context.new_page()
        thread_id = thread_log.id if thread_log else 0
        ACTIVE_PAGES[thread_id] = {"page": page, "context": context}

        # Pre-registration warmup
        _log("Прогрев сессии...")
        try:
            await pre_registration_warmup(page)
        except Exception:
            pass

        # Step 1: Navigate to Google signup
        _log("Открытие страницы регистрации Google...")
        try:
            await page.goto(
                "https://accounts.google.com/signup/v2/webcreateaccount?flowName=GlifWebSignIn&flowEntry=SignUp",
                wait_until="networkidle",
                timeout=60000,
            )
        except Exception as nav_e:
            logger.warning(f"[Gmail] Navigation error: {nav_e}")

        await _human_delay(2, 4)

        # CRITICAL: Check if proxy is dead
        current_url = page.url or ""
        if "chrome-error" in current_url or "about:blank" == current_url:
            _err(f"🔴 Прокси МЁРТВ — страница не загрузилась (URL: {current_url})")
            if proxy:
                try:
                    proxy.status = ProxyStatus.DEAD
                    proxy.fail_count = (proxy.fail_count or 0) + 1
                    db.commit()
                except Exception:
                    pass
            return None

        await random_mouse_move(page, steps=3)
        _log(f"Страница: {page.url}")

        # Step 2: First Name + Last Name
        _log(f"Ввод имени: {first_name} {last_name}")
        fn_sel = await _wait_and_find(page, [
            'input[name="firstName"]', '#firstName',
            'input[aria-label*="irst"]', 'input[aria-label*="имя"]',
            'input[placeholder*="First"]', 'input[placeholder*="имя"]',
            'input[autocomplete="given-name"]',
        ], "gmail_firstname", username, _log, _err, timeout=20000)
        if not fn_sel:
            return None

        await page.locator(fn_sel).first.click()
        await _human_delay(0.3, 0.6)
        for char in first_name:
            await page.locator(fn_sel).first.type(char, delay=random.randint(50, 110))

        ln_sel = await _wait_for_any(page, [
            'input[name="lastName"]', '#lastName',
            'input[aria-label*="ast"]', 'input[aria-label*="фам"]',
            'input[placeholder*="Last"]', 'input[placeholder*="фам"]',
            'input[autocomplete="family-name"]',
        ], timeout=5000)
        if ln_sel:
            await _human_delay(0.3, 0.6)
            for char in last_name:
                await page.locator(ln_sel).first.type(char, delay=random.randint(50, 110))

        await _human_delay(0.5, 1)

        # Click Next
        next_btn = await _wait_for_any(page, [
            'button:has-text("Next")', 'button:has-text("Далее")',
            '#accountDetailsNext button', 'button[type="button"]',
            '#accountDetailsNext', 'div[id*="Next"] button',
            'span:has-text("Next")', 'span:has-text("Далее")',
        ], timeout=5000)
        if next_btn:
            await page.locator(next_btn).first.click()
        else:
            await page.keyboard.press("Enter")
        await _human_delay(3, 5)

        # Check for CAPTCHA after name step
        await _detect_and_solve_recaptcha(page, captcha_provider, _log)
        await between_steps(page)

        # Step 3: Birthday + Gender
        _log("Ввод даты рождения...")
        birthday = generate_birthday()
        month_sel = await _wait_for_any(page, [
            'select#month', '#month', 'select[name="month"]',
            'select[aria-label*="onth"]', 'select[aria-label*="есяц"]',
            '#BirthMonth',
        ], timeout=15000)
        if month_sel:
            await page.locator(month_sel).first.select_option(str(birthday.month))
            await _human_delay(0.3, 0.6)

            day_sel = await _wait_for_any(page, ['input#day', '#day', 'input[name="day"]'], timeout=5000)
            if day_sel:
                await page.locator(day_sel).first.fill(str(birthday.day))

            year_sel = await _wait_for_any(page, ['input#year', '#year', 'input[name="year"]'], timeout=5000)
            if year_sel:
                await page.locator(year_sel).first.fill(str(birthday.year))

            await _human_delay(0.3, 0.6)

            gender_sel = await _wait_for_any(page, ['select#gender', '#gender', 'select[name="gender"]'], timeout=5000)
            if gender_sel:
                await page.locator(gender_sel).first.select_option("1")  # Male

            await _human_delay(0.5, 1)
            next_btn2 = await _wait_for_any(page, ['button:has-text("Next")', 'button:has-text("Далее")', '#birthdaygenderNext button'], timeout=5000)
            if next_btn2:
                await page.locator(next_btn2).first.click()
            else:
                await page.keyboard.press("Enter")
            await _human_delay(3, 5)

        # Step 4: Choose username (Gmail may suggest or let you pick)
        _log(f"Ввод username: {username}")
        # Google may show "Create your own" option or suggested usernames
        create_own = page.locator('div[data-value="custom"], label:has-text("Create your own"), label:has-text("Создайте собственный")')
        try:
            if await create_own.count() > 0:
                await create_own.first.click()
                await _human_delay(1, 2)
        except Exception:
            pass

        username_sel = await _wait_for_any(page, ['input[name="Username"]', '#username', 'input[type="text"][aria-label*="user"]'], timeout=10000)
        if username_sel:
            await page.locator(username_sel).first.click()
            await _human_delay(0.3, 0.6)
            await page.locator(username_sel).first.fill("")
            for char in username:
                await page.locator(username_sel).first.type(char, delay=random.randint(50, 100))
        else:
            _log("Username поле не найдено, возможно Google предложил автовыбор")

        await _human_delay(0.5, 1)
        next_btn3 = await _wait_for_any(page, ['button:has-text("Next")', 'button:has-text("Далее")'], timeout=5000)
        if next_btn3:
            await page.locator(next_btn3).first.click()
        else:
            await page.keyboard.press("Enter")
        await _human_delay(3, 5)

        # Check for username taken error
        err_text = None
        err_el = page.locator('div[class*="error"], div[jsname*="error"], div:has-text("already taken"), div:has-text("уже занято")')
        try:
            if await err_el.count() > 0:
                err_text = await err_el.first.text_content()
        except Exception:
            pass

        if err_text and ("taken" in err_text.lower() or "занято" in err_text.lower()):
            _log(f"Username занят, пробую другой...")
            username = generate_username(first_name, last_name) + str(random.randint(100, 999))
            if username_sel:
                await page.locator(username_sel).first.fill(username)
                await _human_delay(0.5, 1)
                if next_btn3:
                    await page.locator(next_btn3).first.click()
                else:
                    await page.keyboard.press("Enter")
                await _human_delay(3, 5)

        email = f"{username}@gmail.com"
        _log(f"Email будет: {email}")

        # Step 5: Password
        _log("Ввод пароля...")
        pwd_sel = await _wait_and_find(page, [
            'input[name="Passwd"]', 'input[type="password"]', '#passwd',
            'input[aria-label*="assword"]', 'input[aria-label*="арол"]',
            'input[placeholder*="assword"]', 'input[autocomplete="new-password"]',
        ], "gmail_password", username, _log, _err, timeout=20000)
        if not pwd_sel:
            return None

        await page.locator(pwd_sel).first.click()
        await _human_delay(0.3, 0.6)
        for char in password:
            await page.locator(pwd_sel).first.type(char, delay=random.randint(40, 90))

        # Confirm password
        confirm_sel = await _wait_for_any(page, [
            'input[name="PasswdAgain"]', 'input[name="ConfirmPasswd"]',
            'input[aria-label*="onfirm"]', 'input[aria-label*="одтверд"]',
            'input[autocomplete="new-password"]:nth-of-type(2)',
        ], timeout=3000)
        if confirm_sel:
            await _human_delay(0.5, 1)
            await page.locator(confirm_sel).first.click()
            for char in password:
                await page.locator(confirm_sel).first.type(char, delay=random.randint(40, 90))

        await _human_delay(0.5, 1)
        next_btn4 = await _wait_for_any(page, ['button:has-text("Next")', 'button:has-text("Далее")'], timeout=5000)
        if next_btn4:
            await page.locator(next_btn4).first.click()
        else:
            await page.keyboard.press("Enter")
        await _human_delay(3, 5)

        # Step 6: Phone verification (may appear)
        _log("Проверка SMS верификации...")
        phone_sel = await _wait_for_any(page, [
            'input[type="tel"]', 'input[name="phoneNumber"]', '#phoneNumberId',
            'input[aria-label*="hone"]', 'input[aria-label*="елефон"]',
            'input[placeholder*="hone"]', 'input[autocomplete="tel"]',
        ], timeout=10000)
        if phone_sel:
            if not sms_provider:
                _err("Google требует SMS, но SMS провайдер не настроен (SimSMS/GrizzlySMS)")
                return None

            _log("Заказ номера для SMS...")
            _countries = getattr(sms_provider, '_sms_countries', None)
            _blacklist = getattr(sms_provider, '_country_blacklist', None)
            if _countries and hasattr(sms_provider, 'order_number_from_countries'):
                order = await asyncio.to_thread(sms_provider.order_number_from_countries, "gmail", _countries, _blacklist)
            else:
                order = await asyncio.to_thread(sms_provider.order_number, "gmail", "auto")
            if "error" in order:
                _err(f"SMS ошибка: {order['error']}")
                return None

            phone_number = order["number"]
            order_id = order["id"]
            _log(f"Номер: {phone_number}")

            # Format phone for Google (may need +7...)
            display_phone = phone_number if phone_number.startswith("+") else f"+{phone_number}"

            await page.locator(phone_sel).first.click()
            await _human_delay(0.3, 0.6)
            await page.locator(phone_sel).first.fill(display_phone)
            await _human_delay(0.5, 1)

            # Click Next / Send
            send_btn = await _wait_for_any(page, ['button:has-text("Next")', 'button:has-text("Далее")', '#next button'], timeout=5000)
            if send_btn:
                await page.locator(send_btn).first.click()
            else:
                await page.keyboard.press("Enter")

            # Notify SMS service that number was used
            try:
                if hasattr(sms_provider, 'set_status'):
                    await asyncio.to_thread(sms_provider.set_status, order_id, 1)
            except Exception:
                pass

            _log("Ожидание SMS кода...")
            sms_result = await asyncio.to_thread(sms_provider.get_sms_code, order_id, 300, BIRTH_CANCEL_EVENT)

            sms_code = None
            if isinstance(sms_result, dict):
                sms_code = sms_result.get("code")
                if sms_result.get("error"):
                    _err(f"SMS ошибка: {sms_result['error']}")
                    try:
                        await asyncio.to_thread(sms_provider.cancel_number, order_id)
                    except Exception:
                        pass
                    return None
            elif isinstance(sms_result, str):
                sms_code = sms_result

            if not sms_code:
                _err("SMS код не получен")
                try:
                    await asyncio.to_thread(sms_provider.cancel_number, order_id)
                except Exception:
                    pass
                return None

            _log(f"SMS код: {sms_code}")
            code_sel = await _wait_for_any(page, ['input[type="tel"]', 'input[name="code"]', '#code'], timeout=15000)
            if code_sel:
                await page.locator(code_sel).first.fill(sms_code)
                await _human_delay(0.5, 1)
                verify_btn = await _wait_for_any(page, ['button:has-text("Verify")', 'button:has-text("Подтвердить")', 'button:has-text("Next")'], timeout=5000)
                if verify_btn:
                    await page.locator(verify_btn).first.click()
                else:
                    await page.keyboard.press("Enter")

            # Complete SMS activation
            try:
                if hasattr(sms_provider, 'complete_activation'):
                    await asyncio.to_thread(sms_provider.complete_activation, order_id)
            except Exception:
                pass

            await _human_delay(3, 5)
        else:
            _log("SMS не потребовалась (редкость для Gmail)")

        # Step 7: Accept TOS (may show "I agree" button)
        _log("Принятие условий...")
        agree_btn = await _wait_for_any(page, [
            'button:has-text("I agree")', 'button:has-text("Принимаю")',
            'button:has-text("Agree")', 'button:has-text("Next")',
        ], timeout=10000)
        if agree_btn:
            await page.locator(agree_btn).first.click()
            await _human_delay(3, 5)

        # Verify success
        _log(f"Финальный URL: {page.url}")

        # Save session
        try:
            session_path = await browser_manager.save_session(context, 0)
        except Exception:
            session_path = None

        # Create account
        account = Account(
            email=email,
            password=password,
            provider="gmail",
            first_name=first_name,
            last_name=last_name,
            gender="male",
            birthday=birthday,
            birth_ip=f"{proxy.host}" if proxy else None,
            status="new",
        )
        db.add(account)
        db.commit()
        db.refresh(account)

        if session_path:
            try:
                account.browser_profile_path = await browser_manager.save_session(context, account.id)
                db.commit()
            except Exception:
                pass

        logger.info(f"✅ Gmail registered: {email}")
        return account

    except Exception as e:
        logger.error(f"❌ Gmail registration failed: {e}", exc_info=True)
        _err(str(e)[:500])
        return None
    finally:
        ACTIVE_PAGES.pop(thread_id, None)
        try:
            await context.close()
        except Exception:
            pass


async def register_single_yahoo(
    browser_manager: BrowserManager,
    proxy: Proxy | None,
    device_type: str,
    name_pool: list,
    sms_provider,
    db: Session,
    thread_log: ThreadLog | None = None,
    captcha_provider: CaptchaProvider | None = None,
) -> Account | None:
    """Register a single Yahoo account on desktop. Requires SMS."""
    if not name_pool:
        logger.error("[Yahoo] ❌ Нет имён! Загрузите пакет имён перед регистрацией.")
        if thread_log:
            thread_log.status = "error"
            thread_log.error_message = "Нет имён! Загрузите пакет имён."
            try: db.commit()
            except: pass
        return None
    first_name, last_name = random.choice(name_pool)
    password = generate_password()
    username = generate_username(first_name, last_name)
    birthday = generate_birthday()

    context = await browser_manager.create_context(
        proxy=proxy,
        device_type="desktop",
        geo=None,
    )

    def _log(msg: str):
        wid = getattr(thread_log, '_worker_id', '?') if thread_log else '?'
        logger.info(f"[Yahoo][W{wid}] {msg}")
        if thread_log:
            thread_log.current_action = f"[W{wid}] {msg}"
            try:
                db.commit()
            except Exception:
                pass

    def _err(msg: str):
        wid = getattr(thread_log, '_worker_id', '?') if thread_log else '?'
        logger.error(f"[Yahoo][W{wid}] {msg}")
        if thread_log:
            thread_log.error_message = f"[W{wid}] {msg}"[:500]
            try:
                db.commit()
            except Exception:
                pass

    try:
        page = await context.new_page()
        thread_id = thread_log.id if thread_log else 0
        ACTIVE_PAGES[thread_id] = {"page": page, "context": context}

        # Pre-registration warmup
        _log("Прогрев сессии...")
        try:
            await pre_registration_warmup(page)
        except Exception:
            pass

        # Step 1: Navigate to Yahoo signup
        _log("Открытие страницы регистрации Yahoo...")
        try:
            await page.goto(
                "https://login.yahoo.com/account/create",
                wait_until="networkidle",
                timeout=60000,
            )
        except Exception as nav_e:
            logger.warning(f"[Yahoo] Navigation error: {nav_e}")

        await _human_delay(2, 4)

        # CRITICAL: Check if proxy is dead
        current_url = page.url or ""
        if "chrome-error" in current_url or "about:blank" == current_url:
            _err(f"🔴 Прокси МЁРТВ — страница не загрузилась (URL: {current_url})")
            if proxy:
                try:
                    proxy.status = ProxyStatus.DEAD
                    proxy.fail_count = (proxy.fail_count or 0) + 1
                    db.commit()
                except Exception:
                    pass
            return None

        # Check if Yahoo returned error page (E500, rate limit, etc.)
        if "/account/create/error" in current_url or "error" in current_url.split("?")[0].split("/")[-1:]:
            _err(f"🔴 Yahoo вернул страницу ошибки — IP заблокирован или лимит (URL: {current_url})")
            return None

        await random_mouse_move(page, steps=3)
        _log(f"Страница: {page.url}")

        # Yahoo: all fields on one page — fill with human-like behavior
        _log(f"Ввод данных: {first_name} {last_name} / {username}")
        await _debug_screenshot(page, "1_yahoo_form_loaded", _log)

        # First name
        fn_sel = await _wait_and_find(page, [
            'input[name="firstName"]', '#usernamereg-firstName',
            'input[aria-label*="irst"]', 'input[aria-label*="имя"]',
            'input[placeholder*="First"]', 'input[placeholder*="имя"]',
            'input[autocomplete="given-name"]',
        ], "yahoo_firstname", username, _log, _err, timeout=20000)
        if not fn_sel:
            return None

        await _human_fill(page, fn_sel, first_name)
        await _human_delay(1.0, 2.5)  # Human reads before next field

        # Last name
        ln_sel = await _wait_for_any(page, [
            'input[name="lastName"]', '#usernamereg-lastName',
            'input[aria-label*="ast"]', 'input[aria-label*="фам"]',
            'input[placeholder*="Last"]', 'input[placeholder*="фам"]',
            'input[autocomplete="family-name"]',
        ], timeout=5000)
        if ln_sel:
            await _human_fill(page, ln_sel, last_name)
            await _human_delay(1.2, 2.8)

        # Small scroll down — humans do this
        await page.mouse.wheel(0, random.randint(50, 150))
        await _human_delay(0.5, 1.0)

        # Email / Username
        email_sel = await _wait_for_any(page, [
            'input[name="yid"]', '#usernamereg-yid', 'input[name="userId"]',
            'input[aria-label*="user"]', 'input[aria-label*="email"]',
            'input[placeholder*="email"]', 'input[placeholder*="user"]',
        ], timeout=5000)
        if email_sel:
            await _human_fill(page, email_sel, username)
            await _human_delay(1.5, 3.0)  # Human thinks about username

        # Password
        pwd_sel = await _wait_for_any(page, [
            'input[name="password"]', '#usernamereg-password', 'input[type="password"]',
            'input[aria-label*="assword"]', 'input[aria-label*="арол"]',
            'input[placeholder*="assword"]',
        ], timeout=5000)
        if pwd_sel:
            await _human_fill(page, pwd_sel, password)
            await _human_delay(1.0, 2.0)

        # Birthday — scroll down a bit first
        await page.mouse.wheel(0, random.randint(30, 80))
        await _human_delay(0.5, 1.0)

        # Yahoo birthday: input[type="tel"] fields, NOT selects
        month_sel = await _wait_for_any(page, [
            'input[name="mm"]', 'input[placeholder="MM"]',
            'input[placeholder*="onth"]', 'input[aria-label*="onth"]',
        ], timeout=5000)
        if month_sel:
            await _human_fill(page, month_sel, str(birthday.month).zfill(2))
            await _human_delay(0.5, 1.2)

        day_sel = await _wait_for_any(page, [
            'input[name="dd"]', 'input[placeholder="DD"]',
            'input[placeholder*="ay"]', 'input[aria-label*="ay"]',
        ], timeout=3000)
        if day_sel:
            await _human_fill(page, day_sel, str(birthday.day))
            await _human_delay(0.5, 1.0)

        year_sel = await _wait_for_any(page, [
            'input[name="yyyy"]', 'input[placeholder="YYYY"]',
            'input[placeholder*="ear"]', 'input[aria-label*="ear"]',
        ], timeout=3000)
        if year_sel:
            await _human_fill(page, year_sel, str(birthday.year))

        await _human_delay(1.5, 3.0)  # Human reviews form before submitting

        # Scroll to checkbox and Next button
        await page.mouse.wheel(0, random.randint(100, 200))
        await _human_delay(0.8, 1.5)

        # ── CHECK "I agree to these terms" CHECKBOX ──
        # This is REQUIRED by Yahoo — form won't submit without it!
        agree_checkbox = await _wait_for_any(page, [
            'input[type="checkbox"]#consent-agree',
            'input[type="checkbox"][name*="agree"]',
            'input[type="checkbox"][name*="consent"]',
            'label:has-text("I agree") input[type="checkbox"]',
            'input[type="checkbox"]',
        ], timeout=5000)
        if agree_checkbox:
            try:
                is_checked = await page.locator(agree_checkbox).first.is_checked()
                if not is_checked:
                    await _human_click(page, agree_checkbox)
                    _log("☑️ Чекбокс 'I agree' — поставлен")
                    await _human_delay(0.5, 1.0)
            except Exception:
                # Fallback: try clicking the label
                try:
                    label = await _wait_for_any(page, [
                        'label:has-text("I agree")', 'label:has-text("agree to")',
                        'label:has-text("согласен")', 'label:has-text("Принимаю")',
                    ], timeout=2000)
                    if label:
                        await _human_click(page, label)
                        _log("☑️ Чекбокс 'I agree' — поставлен через label")
                except Exception:
                    _log("⚠️ Не удалось поставить чекбокс")
        else:
            _log("Чекбокс согласия не найден — возможно не требуется")

        await _human_delay(0.5, 1.0)

        # Click Next / Continue / Submit
        await _debug_screenshot(page, "2_yahoo_form_filled", _log)
        _log("Отправка формы (Next)...")
        submit_btn = await _wait_for_any(page, [
            'button:has-text("Next")', 'button:has-text("Далее")',
            'button[type="submit"]', '#reg-submit-button',
            'button:has-text("Continue")', 'button:has-text("Продолжить")',
            '#usernamereg-submitBtn',
        ], timeout=5000)
        if submit_btn:
            try:
                await page.locator(submit_btn).first.wait_for(state="attached", timeout=3000)
                await _human_click(page, submit_btn)
            except Exception:
                _log("Кнопка disabled — пробуем Enter...")
                await page.keyboard.press("Enter")
        else:
            await page.keyboard.press("Enter")

        await _human_delay(4, 8)  # Longer wait for page transition

        # ── Post-submit: Handle Yahoo's "Add your phone number" page ──
        post_url = page.url
        _log(f"После отправки: {post_url}")
        await _debug_screenshot(page, "3_yahoo_after_submit", _log)

        # Check for reCAPTCHA after submit
        await _detect_and_solve_recaptcha(page, captcha_provider, _log)
        await _human_delay(1, 2)

        # Yahoo shows a separate "Add your phone number" page after registration
        # We need to detect it, ORDER the SMS number, fill phone, and click "Get code by text"
        phone_page_input = await _wait_for_any(page, [
            'input[name="phone"]', 'input#phone-number',
            'input[placeholder*="hone"]', 'input[aria-label*="hone"]',
            'input[data-type="phone"]', 'input[autocomplete="tel"]',
        ], timeout=15000)

        if phone_page_input:
            _log("📱 Обнаружена страница 'Add your phone number'")
            await _debug_screenshot(page, "4_yahoo_phone_page", _log)

            if not sms_provider:
                _err("Yahoo требует SMS, но SMS провайдер не настроен")
                return None

            # ── Order SMS number NOW (on page 2) ──
            _log("Заказ номера для Yahoo SMS...")
            _countries = getattr(sms_provider, '_sms_countries', None)
            _blacklist = getattr(sms_provider, '_country_blacklist', None)
            if _countries and hasattr(sms_provider, 'order_number_from_countries'):
                order = await asyncio.to_thread(sms_provider.order_number_from_countries, "yahoo", _countries, _blacklist)
            else:
                order = await asyncio.to_thread(sms_provider.order_number, "yahoo", "auto")
            if "error" in order:
                _err(f"SMS ошибка: {order['error']}")
                return None

            phone_number = order["number"]
            order_id = order["id"]
            sms_country = order.get("country", "")
            display_phone = phone_number if phone_number.startswith("+") else f"+{phone_number}"
            _log(f"Номер: {display_phone} (страна: {sms_country})")

            # ── Strip phone prefix to get local number ──
            PHONE_COUNTRY_MAP = {
                "ru": "7", "ua": "380", "kz": "7", "cn": "86", "ph": "63", "id": "62",
                "my": "60", "ke": "254", "tz": "255", "br": "55", "us": "1", "us_v": "1",
                "il": "972", "hk": "852", "pl": "48", "uk": "44", "ng": "234", "eg": "20",
                "in": "91", "ie": "353", "za": "27", "ro": "40", "co": "57", "ee": "372",
                "ca": "1", "de": "49", "nl": "31", "at": "43", "th": "66", "mx": "52",
                "es": "34", "tr": "90", "cz": "420", "pe": "51", "nz": "64", "se": "46",
                "fr": "33", "ar": "54", "vn": "84", "bd": "880", "pk": "92", "cl": "56",
                "be": "32", "bg": "359", "hu": "36", "it": "39", "pt": "351", "gr": "30",
                "fi": "358", "dk": "45", "no": "47", "ch": "41", "au": "61", "jp": "81",
                "ge": "995", "ae": "971", "sa": "966", "cr": "506", "gt": "502", "sk": "421",
                "am": "374", "az": "994", "by": "375", "md": "373", "al": "355", "rs": "381",
                "hr": "385", "si": "386", "lv": "371", "lt": "370", "uy": "598", "bo": "591",
            }
            # SMS country code → ISO alpha-2 for Yahoo's country dropdown
            COUNTRY_TO_ISO2 = {
                "ru": "RU", "ua": "UA", "kz": "KZ", "cn": "CN", "ph": "PH", "id": "ID",
                "my": "MY", "ke": "KE", "tz": "TZ", "br": "BR", "us": "US", "us_v": "US",
                "il": "IL", "hk": "HK", "pl": "PL", "uk": "GB", "ng": "NG", "eg": "EG",
                "in": "IN", "ie": "IE", "za": "ZA", "ro": "RO", "co": "CO", "ee": "EE",
                "ca": "CA", "de": "DE", "nl": "NL", "at": "AT", "th": "TH", "mx": "MX",
                "es": "ES", "tr": "TR", "cz": "CZ", "pe": "PE", "nz": "NZ", "se": "SE",
                "fr": "FR", "ar": "AR", "vn": "VN", "bd": "BD", "pk": "PK", "cl": "CL",
                "be": "BE", "bg": "BG", "hu": "HU", "it": "IT", "pt": "PT", "gr": "GR",
                "fi": "FI", "dk": "DK", "no": "NO", "ch": "CH", "au": "AU", "jp": "JP",
                "ge": "GE", "ae": "AE", "sa": "SA", "cr": "CR", "gt": "GT", "sk": "SK",
                "am": "AM", "az": "AZ", "by": "BY", "md": "MD", "al": "AL", "rs": "RS",
                "hr": "HR", "si": "SI", "lv": "LV", "lt": "LT", "uy": "UY", "bo": "BO",
            }

            phone_prefix = PHONE_COUNTRY_MAP.get(sms_country)
            local_number = phone_number.lstrip("+")
            if phone_prefix and local_number.startswith(phone_prefix):
                local_number = local_number[len(phone_prefix):]
                _log(f"Стрипнули префикс +{phone_prefix}, вводим: {local_number}")
            else:
                _log(f"Вводим как есть: {local_number}")

            # ── CRITICAL: Change Yahoo's country code dropdown to match SMS number ──
            # Yahoo auto-sets country from proxy GEO, but SMS number may be from different country
            # Yahoo uses a CUSTOM UI (clickable button → popup list), NOT a standard <select>
            target_iso = COUNTRY_TO_ISO2.get(sms_country, "").upper()
            country_changed = False

            if target_iso and phone_prefix:
                _log(f"Меняем код страны в Yahoo: → {target_iso} (+{phone_prefix})")
                try:
                    # Strategy 1: Try standard <select> first (some Yahoo versions)
                    select_el = page.locator('select')
                    if await select_el.count() > 0:
                        try:
                            await select_el.first.select_option(value=target_iso)
                            country_changed = True
                            _log(f"✅ Код страны выбран через <select>: {target_iso}")
                        except Exception:
                            try:
                                await select_el.first.select_option(value=target_iso.lower())
                                country_changed = True
                                _log(f"✅ Код страны выбран через <select> (lower): {target_iso.lower()}")
                            except Exception:
                                pass

                    # Strategy 2: Click the country code button to open picker
                    if not country_changed:
                        # Yahoo's country code is a clickable element near the phone input
                        cc_btn = page.locator(
                            'button:near(input[type="tel"]):first, '
                            '[data-country-code], '
                            '.phone-country-code, '
                            '#phone-country-code'
                        )
                        # Also try finding any element containing the current code like +381
                        cc_elements = page.locator(f'[class*="country"], [id*="country"], button:has-text("+")')

                        clicked = False
                        for locator in [cc_btn, cc_elements]:
                            try:
                                if await locator.count() > 0:
                                    await locator.first.click()
                                    await _human_delay(1.0, 2.0)
                                    clicked = True
                                    _log("Открыли пикер кода страны")
                                    break
                            except Exception:
                                continue

                        if clicked:
                            # Look for search input in the popup
                            search_input = page.locator(
                                'input[type="search"], input[type="text"][placeholder*="earch"], '
                                'input[type="text"][placeholder*="ountr"], input[aria-label*="earch"]'
                            )
                            if await search_input.count() > 0:
                                await search_input.first.fill(f"+{phone_prefix}")
                                await _human_delay(1.0, 1.5)
                                _log(f"Поиск в пикере: +{phone_prefix}")

                            # Click the option matching our country
                            option = page.locator(
                                f'li:has-text("+{phone_prefix}"), '
                                f'div[role="option"]:has-text("+{phone_prefix}"), '
                                f'a:has-text("+{phone_prefix}"), '
                                f'[data-value="{target_iso}"], '
                                f'[data-country="{target_iso}"]'
                            )
                            try:
                                if await option.count() > 0:
                                    await option.first.click()
                                    country_changed = True
                                    _log(f"✅ Код страны выбран через пикер: +{phone_prefix}")
                                    await _human_delay(0.5, 1.0)
                            except Exception as e:
                                _log(f"⚠️ Не удалось кликнуть опцию: {e}")
                                # Close popup by pressing Escape
                                await page.keyboard.press("Escape")
                                await _human_delay(0.5, 1.0)

                    # Strategy 3: JavaScript — force-change the country code
                    if not country_changed:
                        _log("Пробуем JS для смены кода страны...")
                        try:
                            # Try to find and change any select elements via JS
                            changed = await page.evaluate(f"""() => {{
                                // Try standard selects
                                const selects = document.querySelectorAll('select');
                                for (const sel of selects) {{
                                    for (const opt of sel.options) {{
                                        if (opt.value === '{target_iso}' || opt.value === '{target_iso.lower()}'
                                            || opt.text.includes('+{phone_prefix}')
                                            || opt.value === '{phone_prefix}') {{
                                            sel.value = opt.value;
                                            sel.dispatchEvent(new Event('change', {{bubbles: true}}));
                                            return true;
                                        }}
                                    }}
                                }}
                                return false;
                            }}""")
                            if changed:
                                country_changed = True
                                _log(f"✅ Код страны изменён через JS")
                        except Exception:
                            pass

                except Exception as e:
                    _log(f"⚠️ Ошибка смены кода страны: {e}")

            # ── If country code change failed, enter FULL international number ──
            if not country_changed and phone_prefix:
                _log(f"⚠️ Не удалось сменить код страны — вводим полный номер +{phone_prefix}{local_number}")
                # Clear field and enter full number including country code
                local_number = f"{phone_prefix}{local_number}"

            # Human-like: read the page text first (real person would read instructions)
            await random_mouse_move(page, steps=3)
            await _human_delay(3.0, 5.0)  # Read "Add your phone number" text

            # Small scroll to see the full form
            await page.mouse.wheel(0, random.randint(30, 80))
            await _human_delay(0.8, 1.5)

            # Clear field first (in case Yahoo pre-filled something)
            try:
                await page.locator(phone_page_input).first.fill("")
                await _human_delay(0.3, 0.5)
            except Exception:
                pass

            # Fill the phone number with human typing
            await _human_fill(page, phone_page_input, local_number)
            _log(f"Ввели номер: {local_number}")
            await _human_delay(1.5, 3.0)

            # Take screenshot AFTER filling to verify
            await _debug_screenshot(page, "4b_yahoo_phone_filled", _log)

            # Human reads terms, looks at button before clicking (2-4 seconds)
            await random_mouse_move(page, steps=2)
            await _human_delay(2.0, 4.0)

            # Click "Get code by text" button (the purple button)
            get_code_btn = await _wait_for_any(page, [
                'button:has-text("Get code by text")',
                'button:has-text("code by text")',
                'button:has-text("Получить код")',
                'button:has-text("Text me")',
                'button:has-text("Send code")',
                'button[type="submit"]',
                'button[data-type="sms"]',
                '#send-code-button',
            ], timeout=5000)

            if get_code_btn:
                _log("📲 Нажимаем 'Get code by text'...")
                await _human_click(page, get_code_btn)
                await _human_delay(5, 8)  # Longer wait for response

                # Check for challenge/fail — Yahoo blocked us
                curr = page.url
                _log(f"После нажатия 'Get code': {curr}")
                await _debug_screenshot(page, "5_yahoo_after_getcode", _log)
                if 'challenge/fail' in curr or 'error' in curr:
                    _err("🔴 Yahoo заблокировал: challenge/fail — попробуй другой прокси")
                    try:
                        await asyncio.to_thread(sms_provider.cancel_number, order_id)
                    except Exception:
                        pass
                    return None
            else:
                _log("⚠️ Кнопка 'Get code by text' не найдена — пробуем Enter")
                await page.keyboard.press("Enter")
                await _human_delay(4, 7)
        else:
            _log("⚠️ Страница телефона не найдена — Yahoo мог не перейти на следующий шаг")
            await _debug_screenshot(page, "4_yahoo_no_phone_page", _log)
            return None

        # Check for reCAPTCHA after phone submit
        await _detect_and_solve_recaptcha(page, captcha_provider, _log)
        await _human_delay(1, 2)

        # SMS verification
        if order_id:
            try:
                if hasattr(sms_provider, 'set_status'):
                    await asyncio.to_thread(sms_provider.set_status, order_id, 1)
            except Exception:
                pass

            _log("Ожидание SMS кода Yahoo...")
            _log(f"Страница: {page.url}")

            # Yahoo uses 6 individual digit inputs: #verify-code-0 to #verify-code-5
            first_digit = await _wait_for_any(page, [
                'input#verify-code-0', 'input[aria-label="Code 1"]',
                'input[name="code"]', 'input[name="verificationCode"]',
            ], timeout=15000)

            if first_digit:
                _log(f"✅ Поле SMS кода найдено: {first_digit}")
            else:
                _log("⚠️ Поле SMS кода НЕ НАЙДЕНО — Yahoo не показал форму верификации!")

            sms_result = await asyncio.to_thread(sms_provider.get_sms_code, order_id, 300, BIRTH_CANCEL_EVENT)
            sms_code = None
            if isinstance(sms_result, dict):
                sms_code = sms_result.get("code")
                if sms_result.get("error"):
                    _err(f"SMS ошибка: {sms_result['error']}")
                    try:
                        await asyncio.to_thread(sms_provider.cancel_number, order_id)
                    except Exception:
                        pass
                    return None
            elif isinstance(sms_result, str):
                sms_code = sms_result

            if not sms_code:
                _err("SMS код не получен")
                try:
                    await asyncio.to_thread(sms_provider.cancel_number, order_id)
                except Exception:
                    pass
                return None

            _log(f"SMS код: {sms_code}")
            # Enter code digit by digit into 6 individual inputs
            code_digits = str(sms_code).strip()
            for i, digit in enumerate(code_digits[:6]):
                digit_sel = f'input#verify-code-{i}'
                try:
                    await page.locator(digit_sel).first.fill(digit)
                    await _human_delay(0.1, 0.3)
                except Exception:
                    # Fallback: try single input field
                    if first_digit:
                        await page.locator(first_digit).first.fill(code_digits)
                    break
            await _human_delay(0.5, 1)

            # Click verify/next button
            verify_btn = await _wait_for_any(page, [
                'button[name="validate"]',
                'button:has-text("Verify")', 'button:has-text("Next")',
                'button[type="submit"]',
            ], timeout=5000)
            if verify_btn:
                await page.locator(verify_btn).first.click()
            else:
                await page.keyboard.press("Enter")

            try:
                if hasattr(sms_provider, 'complete_activation'):
                    await asyncio.to_thread(sms_provider.complete_activation, order_id)
            except Exception:
                pass

            await _human_delay(3, 5)

        email = f"{username}@yahoo.com"
        _log(f"Финальный URL: {page.url}")

        # Save session
        try:
            session_path = await browser_manager.save_session(context, 0)
        except Exception:
            session_path = None

        account = Account(
            email=email,
            password=password,
            provider="yahoo",
            first_name=first_name,
            last_name=last_name,
            gender="random",
            birthday=birthday,
            birth_ip=f"{proxy.host}" if proxy else None,
            status="new",
        )
        db.add(account)
        db.commit()
        db.refresh(account)

        if session_path:
            try:
                account.browser_profile_path = await browser_manager.save_session(context, account.id)
                db.commit()
            except Exception:
                pass

        logger.info(f"✅ Yahoo registered: {email}")
        return account

    except Exception as e:
        logger.error(f"❌ Yahoo registration failed: {e}", exc_info=True)
        _err(str(e)[:500])
        return None
    finally:
        ACTIVE_PAGES.pop(thread_id, None)
        try:
            await context.close()
        except Exception:
            pass


async def register_single_aol(
    browser_manager: BrowserManager,
    proxy: Proxy | None,
    device_type: str,
    name_pool: list,
    sms_provider,
    db: Session,
    thread_log: ThreadLog | None = None,
    captcha_provider: CaptchaProvider | None = None,
) -> Account | None:
    """Register a single AOL account on desktop. Requires SMS. (AOL = Yahoo/Verizon family)."""
    if not name_pool:
        logger.error("[AOL] ❌ Нет имён! Загрузите пакет имён перед регистрацией.")
        if thread_log:
            thread_log.status = "error"
            thread_log.error_message = "Нет имён! Загрузите пакет имён."
            try: db.commit()
            except: pass
        return None
    first_name, last_name = random.choice(name_pool)
    password = generate_password()
    username = generate_username(first_name, last_name)
    birthday = generate_birthday()

    context = await browser_manager.create_context(
        proxy=proxy,
        device_type="desktop",
        geo=None,
    )

    def _log(msg: str):
        wid = getattr(thread_log, '_worker_id', '?') if thread_log else '?'
        logger.info(f"[AOL][W{wid}] {msg}")
        if thread_log:
            thread_log.current_action = f"[W{wid}] {msg}"
            try:
                db.commit()
            except Exception:
                pass

    def _err(msg: str):
        wid = getattr(thread_log, '_worker_id', '?') if thread_log else '?'
        logger.error(f"[AOL][W{wid}] {msg}")
        if thread_log:
            thread_log.error_message = f"[W{wid}] {msg}"[:500]
            try:
                db.commit()
            except Exception:
                pass

    try:
        page = await context.new_page()
        thread_id = thread_log.id if thread_log else 0
        ACTIVE_PAGES[thread_id] = {"page": page, "context": context}

        # Pre-registration warmup
        _log("Прогрев сессии...")
        try:
            await pre_registration_warmup(page)
        except Exception:
            pass

        # Step 1: Navigate to AOL signup
        _log("Открытие страницы регистрации AOL...")
        try:
            await page.goto(
                "https://login.aol.com/account/create",
                wait_until="networkidle",
                timeout=60000,
            )
        except Exception as nav_e:
            logger.warning(f"[AOL] Navigation error: {nav_e}")

        await _human_delay(2, 4)

        # CRITICAL: Check if proxy is dead
        current_url = page.url or ""
        if "chrome-error" in current_url or "about:blank" == current_url:
            _err(f"🔴 Прокси МЁРТВ — страница не загрузилась (URL: {current_url})")
            if proxy:
                try:
                    proxy.status = ProxyStatus.DEAD
                    proxy.fail_count = (proxy.fail_count or 0) + 1
                    db.commit()
                except Exception:
                    pass
            return None

        await random_mouse_move(page, steps=3)
        _log(f"Страница: {page.url}")

        # AOL: all fields on one page (same as Yahoo layout)
        _log(f"Ввод данных: {first_name} {last_name} / {username}")
        fn_sel = await _wait_and_find(page, [
            'input[name="firstName"]', '#usernamereg-firstName',
            'input[aria-label*="irst"]', 'input[aria-label*="имя"]',
            'input[placeholder*="First"]', 'input[placeholder*="имя"]',
            'input[autocomplete="given-name"]',
        ], "aol_firstname", username, _log, _err, timeout=20000)
        if not fn_sel:
            return None

        await page.locator(fn_sel).first.click()
        await _human_delay(0.3, 0.6)
        for char in first_name:
            await page.locator(fn_sel).first.type(char, delay=random.randint(50, 110))

        # Last name
        ln_sel = await _wait_for_any(page, [
            'input[name="lastName"]', '#usernamereg-lastName',
            'input[aria-label*="ast"]', 'input[aria-label*="фам"]',
            'input[placeholder*="Last"]', 'input[placeholder*="фам"]',
            'input[autocomplete="family-name"]',
        ], timeout=5000)
        if ln_sel:
            await _human_delay(0.3, 0.6)
            for char in last_name:
                await page.locator(ln_sel).first.type(char, delay=random.randint(50, 110))

        # Email / Username
        email_sel = await _wait_for_any(page, [
            'input[name="yid"]', '#usernamereg-yid', 'input[name="userId"]',
            'input[aria-label*="user"]', 'input[aria-label*="email"]',
            'input[placeholder*="email"]', 'input[placeholder*="user"]',
        ], timeout=5000)
        if email_sel:
            await _human_delay(0.3, 0.6)
            await page.locator(email_sel).first.fill("")
            for char in username:
                await page.locator(email_sel).first.type(char, delay=random.randint(50, 100))

        # Password
        pwd_sel = await _wait_for_any(page, [
            'input[name="password"]', '#usernamereg-password', 'input[type="password"]',
            'input[aria-label*="assword"]', 'input[aria-label*="арол"]',
            'input[placeholder*="assword"]',
        ], timeout=5000)
        if pwd_sel:
            await _human_delay(0.3, 0.6)
            for char in password:
                await page.locator(pwd_sel).first.type(char, delay=random.randint(40, 90))

        # Phone number — AOL requires it
        phone_sel = await _wait_for_any(page, [
            'input[name="phone"]', '#usernamereg-phone', 'input[type="tel"]',
            'input[aria-label*="hone"]', 'input[aria-label*="елеф"]',
            'input[placeholder*="hone"]', 'input[autocomplete="tel"]',
        ], timeout=5000)
        order_id = None
        if phone_sel:
            if not sms_provider:
                _err("AOL требует SMS, но SMS провайдер не настроен")
                return None

            _log("Заказ номера для AOL SMS...")
            _countries = getattr(sms_provider, '_sms_countries', None)
            _blacklist = getattr(sms_provider, '_country_blacklist', None)
            if _countries and hasattr(sms_provider, 'order_number_from_countries'):
                order = await asyncio.to_thread(sms_provider.order_number_from_countries, "aol", _countries, _blacklist)
            else:
                order = await asyncio.to_thread(sms_provider.order_number, "aol", "auto")
            if "error" in order:
                # AOL service might not exist, try "any"
                _log("Пробую заказать номер как 'any'...")
                if _countries and hasattr(sms_provider, 'order_number_from_countries'):
                    order = await asyncio.to_thread(sms_provider.order_number_from_countries, "any", _countries, _blacklist)
                else:
                    order = await asyncio.to_thread(sms_provider.order_number, "any", "auto")
            if "error" in order:
                _err(f"SMS ошибка: {order['error']}")
                return None

            phone_number = order["number"]
            order_id = order["id"]
            display_phone = phone_number if phone_number.startswith("+") else f"+{phone_number}"
            _log(f"Номер: {display_phone}")

            await page.locator(phone_sel).first.click()
            await _human_delay(0.3, 0.6)
            await page.locator(phone_sel).first.fill(display_phone)

        # Birthday
        month_sel = await _wait_for_any(page, [
            'select#usernamereg-month', 'select[name="mm"]', '#usernamereg-month',
            'select[aria-label*="onth"]', 'select[aria-label*="есяц"]',
        ], timeout=5000)
        if month_sel:
            await _human_delay(0.3, 0.5)
            await page.locator(month_sel).first.select_option(str(birthday.month))

        day_sel = await _wait_for_any(page, [
            'input#usernamereg-day', 'input[name="dd"]', '#usernamereg-day',
            'input[aria-label*="ay"]', 'input[placeholder*="ay"]',
        ], timeout=3000)
        if day_sel:
            await page.locator(day_sel).first.fill(str(birthday.day))

        year_sel = await _wait_for_any(page, [
            'input#usernamereg-year', 'input[name="yyyy"]', '#usernamereg-year',
            'input[aria-label*="ear"]', 'input[placeholder*="ear"]',
        ], timeout=3000)
        if year_sel:
            await page.locator(year_sel).first.fill(str(birthday.year))

        await _human_delay(0.5, 1)

        # Submit
        _log("Отправка формы...")
        submit_btn = await _wait_for_any(page, [
            'button[type="submit"]', '#reg-submit-button',
            'button:has-text("Continue")', 'button:has-text("Продолжить")',
            '#usernamereg-submitBtn',
        ], timeout=5000)
        if submit_btn:
            await page.locator(submit_btn).first.click()
        else:
            await page.keyboard.press("Enter")

        await _human_delay(3, 6)

        # Check for reCAPTCHA after submit
        await _detect_and_solve_recaptcha(page, captcha_provider, _log)
        await _human_delay(1, 2)

        # SMS verification
        if order_id:
            try:
                if hasattr(sms_provider, 'set_status'):
                    await asyncio.to_thread(sms_provider.set_status, order_id, 1)
            except Exception:
                pass

            _log("Ожидание SMS кода AOL...")
            sms_code_sel = await _wait_for_any(page, [
                'input[name="code"]', 'input[type="tel"]',
                'input[name="verificationCode"]',
            ], timeout=15000)

            sms_result = await asyncio.to_thread(sms_provider.get_sms_code, order_id, 300, BIRTH_CANCEL_EVENT)
            sms_code = None
            if isinstance(sms_result, dict):
                sms_code = sms_result.get("code")
                if sms_result.get("error"):
                    _err(f"SMS ошибка: {sms_result['error']}")
                    try:
                        await asyncio.to_thread(sms_provider.cancel_number, order_id)
                    except Exception:
                        pass
                    return None
            elif isinstance(sms_result, str):
                sms_code = sms_result

            if not sms_code:
                _err("SMS код не получен")
                try:
                    await asyncio.to_thread(sms_provider.cancel_number, order_id)
                except Exception:
                    pass
                return None

            _log(f"SMS код: {sms_code}")
            if sms_code_sel:
                await page.locator(sms_code_sel).first.fill(sms_code)
                await _human_delay(0.5, 1)
                verify_btn = await _wait_for_any(page, [
                    'button:has-text("Verify")', 'button[type="submit"]',
                    'button:has-text("Continue")',
                ], timeout=5000)
                if verify_btn:
                    await page.locator(verify_btn).first.click()
                else:
                    await page.keyboard.press("Enter")

            try:
                if hasattr(sms_provider, 'complete_activation'):
                    await asyncio.to_thread(sms_provider.complete_activation, order_id)
            except Exception:
                pass

            await _human_delay(3, 5)

        email = f"{username}@aol.com"
        _log(f"Финальный URL: {page.url}")

        # Save session
        try:
            session_path = await browser_manager.save_session(context, 0)
        except Exception:
            session_path = None

        account = Account(
            email=email,
            password=password,
            provider="aol",
            first_name=first_name,
            last_name=last_name,
            gender="random",
            birthday=birthday,
            birth_ip=f"{proxy.host}" if proxy else None,
            status="new",
        )
        db.add(account)
        db.commit()
        db.refresh(account)

        if session_path:
            try:
                account.browser_profile_path = await browser_manager.save_session(context, account.id)
                db.commit()
            except Exception:
                pass

        logger.info(f"✅ AOL registered: {email}")
        return account

    except Exception as e:
        logger.error(f"❌ AOL registration failed: {e}", exc_info=True)
        _err(str(e)[:500])
        return None
    finally:
        ACTIVE_PAGES.pop(thread_id, None)
        try:
            await context.close()
        except Exception:
            pass



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

        # Create farm
        farm_name = request.farm_name or f"Birth_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        farm = Farm(name=farm_name, description=f"{request.quantity}x {request.provider}")
        db.add(farm)
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
                            )
                        elif request.provider == "hotmail":
                            account = await register_single_outlook(
                                browser_manager, proxy, request.device_type,
                                worker_name_pool, captcha, db, thread_log,
                                domain="hotmail.com",
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
