"""
Leomail v3 — AOL Registration Engine
"""
import asyncio
import random
import threading
from loguru import logger
from sqlalchemy.orm import Session

from ...models import Proxy, ProxyStatus, Account, ThreadLog
from ...services.captcha_provider import CaptchaProvider
from ...utils import generate_birthday, generate_password, generate_username
from ..browser_manager import BrowserManager
from ..human_behavior import (
    random_mouse_move, random_scroll, between_steps,
    pre_registration_warmup, human_click as hb_human_click, warmup_browsing,
)
from ._helpers import (
    human_delay as _human_delay,
    human_fill as _human_fill,
    human_type as _human_type,
    human_click as _human_click,
    check_error_on_page as _check_error_on_page,
    fluent_combobox_select as _fluent_combobox_select,
    wait_for_any as _wait_for_any,
    step_screenshot as _step_screenshot,
    wait_and_find as _wait_and_find,
    detect_and_solve_recaptcha as _detect_and_solve_recaptcha,
    debug_screenshot as _debug_screenshot,
    PHONE_COUNTRY_MAP, COUNTRY_TO_ISO2,
)

async def register_single_aol(
    browser_manager: BrowserManager,
    proxy: Proxy | None,
    device_type: str,
    name_pool: list,
    sms_provider,
    db: Session,
    thread_log: ThreadLog | None = None,
    captcha_provider: CaptchaProvider | None = None,
    ACTIVE_PAGES: dict = None,
    BIRTH_CANCEL_EVENT: threading.Event = None,
) -> Account | None:
    """Register a single AOL account on desktop. Requires SMS. (AOL = Yahoo/Verizon family)."""
    if ACTIVE_PAGES is None:
        ACTIVE_PAGES = {}
    if BIRTH_CANCEL_EVENT is None:
        BIRTH_CANCEL_EVENT = threading.Event()
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
            thread_log.current_action = f"#{thread_log.id} {msg}"
            try:
                db.commit()
            except Exception:
                pass

    def _err(msg: str):
        wid = getattr(thread_log, '_worker_id', '?') if thread_log else '?'
        logger.error(f"[AOL][W{wid}] {msg}")
        if thread_log:
            thread_log.error_message = f"#{thread_log.id} {msg}"[:500]
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
