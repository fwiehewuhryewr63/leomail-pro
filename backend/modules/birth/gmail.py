"""
Leomail v3 — Gmail Registration Engine (with Vision CV)
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
    order_sms_with_chain,
    export_account_to_file,
)

async def register_single_gmail(
    browser_manager: BrowserManager,
    proxy: Proxy | None,
    name_pool: list,
    captcha_provider: CaptchaProvider | None,
    sms_provider,  # SimSmsProvider or GrizzlySMS
    db: Session,
    thread_log: ThreadLog | None = None,
    ACTIVE_PAGES: dict = None,
    BIRTH_CANCEL_EVENT: threading.Event = None,
) -> Account | None:
    """Register a single Gmail account on MOBILE device. Requires SMS."""
    if ACTIVE_PAGES is None:
        ACTIVE_PAGES = {}
    if BIRTH_CANCEL_EVENT is None:
        BIRTH_CANCEL_EVENT = threading.Event()
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
        n = getattr(thread_log, '_worker_id', 0) + 1 if thread_log else '?'
        logger.info(f"[Gmail][Поток {n}] {msg}")
        if thread_log:
            thread_log.current_action = f"Поток {n}: {msg}"
            try:
                db.commit()
            except Exception:
                pass

    def _err(msg: str):
        n = getattr(thread_log, '_worker_id', 0) + 1 if thread_log else '?'
        logger.error(f"[Gmail][Поток {n}] {msg}")
        if thread_log:
            thread_log.error_message = f"Поток {n}: {msg}"[:500]
            try:
                db.commit()
            except Exception:
                pass

    # ── Initialize Vision Engine ──
    vision = None
    try:
        from ..vision import VisionEngine
        vision = VisionEngine("gmail", debug=True)
        _log("👁️ Vision Engine активен")
    except Exception as ve:
        logger.debug(f"[Gmail] Vision not available: {ve}")

    try:
        page = await context.new_page()
        thread_id = thread_log.id if thread_log else 0
        ACTIVE_PAGES[thread_id] = {"page": page, "context": context}

        # Fast warmup — just a quick Google visit (2-3s instead of 15-30s)
        _log("Быстрый прогрев сессии...")
        try:
            await page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=15000)
            await _human_delay(1, 2)
            await random_mouse_move(page, steps=2)
        except Exception:
            pass

        # Step 1: Navigate to Google signup
        _log("Открытие страницы регистрации Google...")
        try:
            await page.goto(
                "https://accounts.google.com/signup/v2/webcreateaccount?flowName=GlifWebSignIn&flowEntry=SignUp",
                wait_until="domcontentloaded",
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

            _log("Заказ номера для Gmail SMS...")
            proxy_geo = getattr(proxy, 'geo', None) if proxy else None

            order, active_sms_provider, expanded_countries = await order_sms_with_chain(
                service="gmail",
                sms_provider=sms_provider,
                proxy_geo=proxy_geo,
                page=None,  # Gmail has no country dropdown
                scrape_dropdown=False,
                _log=_log,
                _err=_err,
            )
            if not order:
                return None

            sms_provider = active_sms_provider

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

        # Verify success — check URL
        final_url = page.url.lower()
        _log(f"Финальный URL: {final_url}")

        registration_success = False
        success_indicators = ["myaccount.google.com", "mail.google.com", "/speedbump", "/interstitial", "/signinchooser"]
        if any(ind in final_url for ind in success_indicators):
            registration_success = True
            _log("✅ URL подтверждает успешную регистрацию")
        elif "accounts.google.com/signup" not in final_url:
            registration_success = True
            _log("✅ Покинули страницу регистрации")
        else:
            _err(f"❌ Регистрация не подтверждена — URL: {final_url}")
            await _debug_screenshot(page, "gmail_not_confirmed", _log)
            return None

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
        export_account_to_file(account)
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
