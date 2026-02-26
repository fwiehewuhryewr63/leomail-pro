"""
Leomail v3 — AOL Registration Engine (with Vision CV)
Upgraded to Yahoo-level: country detection, phone retry, human behavior, challenge handling.
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
    PHONE_COUNTRY_MAP, COUNTRY_TO_ISO2, PREFIX_TO_SMS_COUNTRY,
    order_sms_with_chain, order_sms_retry,
    export_account_to_file,
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
        n = getattr(thread_log, '_worker_id', 0) + 1 if thread_log else '?'
        logger.info(f"[AOL][Поток {n}] {msg}")
        if thread_log:
            thread_log.current_action = f"Поток {n}: {msg}"
            try:
                db.commit()
            except Exception:
                pass

    def _err(msg: str):
        n = getattr(thread_log, '_worker_id', 0) + 1 if thread_log else '?'
        logger.error(f"[AOL][Поток {n}] {msg}")
        if thread_log:
            thread_log.error_message = f"Поток {n}: {msg}"[:500]
            try:
                db.commit()
            except Exception:
                pass

    # ── Initialize Vision Engine (OCR + stage detection) ──
    vision = None
    try:
        from ..vision import VisionEngine
        vision = VisionEngine("aol", debug=True)
        _log("👁️ Vision Engine активен")
    except Exception as ve:
        logger.debug(f"[AOL] Vision not available: {ve}")

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

        # Step 1: Navigate to AOL signup
        _log("Открытие страницы регистрации AOL...")
        try:
            await page.goto(
                "https://login.aol.com/account/create",
                wait_until="domcontentloaded",
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

        # Check if AOL returned error page (E500, rate limit, etc.)
        if "/account/create/error" in current_url or "error" in current_url.split("?")[0].split("/")[-1:]:
            _err(f"🔴 AOL вернул страницу ошибки — IP заблокирован или лимит (URL: {current_url})")
            return None

        await random_mouse_move(page, steps=3)
        _log(f"Страница: {page.url}")

        # AOL: all fields on one page — fill with human-like behavior
        _log(f"Ввод данных: {first_name} {last_name} / {username}")

        # First name
        fn_sel = await _wait_and_find(page, [
            'input[name="firstName"]', '#usernamereg-firstName',
            'input[aria-label*="irst"]', 'input[aria-label*="имя"]',
            'input[placeholder*="First"]', 'input[placeholder*="имя"]',
            'input[autocomplete="given-name"]',
        ], "aol_firstname", username, _log, _err, timeout=20000)
        if not fn_sel:
            return None

        await _human_fill(page, fn_sel, first_name)
        await _human_delay(1.0, 2.5)

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
            'input#reg-userId', 'input[name="userId"]',
            'input[name="yid"]', '#usernamereg-yid',
            'input[aria-label*="user"]', 'input[aria-label*="email"]',
            'input[placeholder*="email"]', 'input[placeholder*="user"]',
        ], timeout=5000)
        if email_sel:
            await _human_fill(page, email_sel, username)
            await _human_delay(1.5, 3.0)

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

        # AOL birthday: input[type="tel"] fields or selects
        month_sel = await _wait_for_any(page, [
            'input[name="mm"]', 'input[placeholder="MM"]',
            'input[placeholder*="onth"]', 'input[aria-label*="onth"]',
            'select#usernamereg-month', 'select[name="mm"]',
        ], timeout=5000)
        if month_sel:
            tag_name = await page.locator(month_sel).first.evaluate("el => el.tagName")
            if tag_name.upper() == "SELECT":
                await page.locator(month_sel).first.select_option(str(birthday.month))
            else:
                await _human_fill(page, month_sel, str(birthday.month).zfill(2))
            await _human_delay(0.5, 1.2)

        day_sel = await _wait_for_any(page, [
            'input[name="dd"]', 'input[placeholder="DD"]',
            'input[placeholder*="ay"]', 'input[aria-label*="ay"]',
            'input#usernamereg-day',
        ], timeout=3000)
        if day_sel:
            await _human_fill(page, day_sel, str(birthday.day))
            await _human_delay(0.5, 1.0)

        year_sel = await _wait_for_any(page, [
            'input[name="yyyy"]', 'input[placeholder="YYYY"]',
            'input[placeholder*="ear"]', 'input[aria-label*="ear"]',
            'input#usernamereg-year',
        ], timeout=3000)
        if year_sel:
            await _human_fill(page, year_sel, str(birthday.year))

        await _human_delay(1.5, 3.0)  # Human reviews form before submitting

        # Scroll to Next button
        await page.mouse.wheel(0, random.randint(100, 200))
        await _human_delay(0.8, 1.5)

        # Click Next / Continue / Submit — with "Email not available" retry
        _log("Отправка формы (Next)...")
        submit_btn = await _wait_for_any(page, [
            'button[name="signup"]',
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

        await _human_delay(4, 8)

        # ── CRITICAL: Detect "Email not available" and retry with new username ──
        for email_retry in range(3):
            try:
                page_text = await page.locator('body').inner_text()
                email_taken_phrases = [
                    "email not available",
                    "not available",
                    "already taken",
                    "уже занят",
                    "недоступен",
                ]
                email_taken = any(p.lower() in page_text.lower() for p in email_taken_phrases)
            except Exception:
                email_taken = False

            if email_taken:
                old_username = username
                username = generate_username(first_name, last_name)
                _log(f"⚠️ Email '{old_username}@aol.com' занят! Пробуем: {username}")
                email_sel_retry = await _wait_for_any(page, [
                    'input[name="yid"]', '#usernamereg-yid', 'input[name="userId"]',
                    'input#reg-userId',
                ], timeout=3000)
                if email_sel_retry:
                    await page.locator(email_sel_retry).first.fill("")
                    await _human_fill(page, email_sel_retry, username)
                    await _human_delay(1, 2)
                    submit_retry = await _wait_for_any(page, [
                        'button:has-text("Next")', 'button[type="submit"]',
                        'button:has-text("Continue")',
                    ], timeout=3000)
                    if submit_retry:
                        await _human_click(page, submit_retry)
                    else:
                        await page.keyboard.press("Enter")
                    await _human_delay(4, 8)
                else:
                    _err("Поле email не найдено для повторного ввода")
                    return None
            else:
                break
        else:
            _err(f"AOL отклонил 3 username подряд — пробуйте другие имена")
            return None

        # ── Post-submit: Handle AOL's "Add your phone number" page ──
        post_url = page.url
        _log(f"После отправки: {post_url}")

        # Check for reCAPTCHA after submit
        await _detect_and_solve_recaptcha(page, captcha_provider, _log)
        await _human_delay(1, 2)

        # AOL shows a separate "Add your phone number" page after registration
        phone_page_input = await _wait_for_any(page, [
            'input#reg-phone', 'input[name="phone"]', 'input#phone-number',
            'input[placeholder*="hone"]', 'input[aria-label*="hone"]',
            'input[data-type="phone"]', 'input[autocomplete="tel"]',
        ], timeout=15000)

        if phone_page_input:
            _log("Обнаружена страница 'Add your phone number'")

            if not sms_provider:
                _err("AOL требует SMS, но SMS провайдер не настроен")
                return None

            # ── STEP 1: Order SMS via shared auto-intelligence ──
            proxy_geo = getattr(proxy, 'geo', None) if proxy else None
            _log("Заказ номера для AOL SMS...")

            order, active_sms_provider, expanded_countries = await order_sms_with_chain(
                service="aol",
                sms_provider=sms_provider,
                proxy_geo=proxy_geo,
                page=page,
                scrape_dropdown=True,
                _log=_log,
                _err=_err,
            )

            if not order:
                return None

            sms_provider = active_sms_provider

            phone_number = order["number"]
            order_id = order["id"]
            sms_country = order.get("country", "")
            display_phone = phone_number if phone_number.startswith("+") else f"+{phone_number}"
            _log(f"Номер: {display_phone} (страна: {sms_country})")

            # ── STEP 3: Strip phone prefix to get local number ──
            phone_prefix = PHONE_COUNTRY_MAP.get(sms_country)
            local_number = phone_number.lstrip("+")
            if phone_prefix and local_number.startswith(phone_prefix):
                local_number = local_number[len(phone_prefix):]
                _log(f"Стрипнули префикс +{phone_prefix}, вводим: {local_number}")
            else:
                _log(f"Вводим как есть: {local_number}")

            # ── STEP 4: Change AOL's country code IF it doesn't match ──
            # Detect what country AOL is currently showing on the page
            aol_page_prefix = None
            try:
                aol_page_prefix = await page.evaluate("""() => {
                    const selects = document.querySelectorAll('select[id^="countryCode"], select');
                    for (const sel of selects) {
                        const opt = sel.options[sel.selectedIndex];
                        if (opt) {
                            const m = opt.text.match(/\\+(\\d{1,4})/);
                            if (m) return m[1];
                        }
                    }
                    const inputs = document.querySelectorAll('input');
                    for (const inp of inputs) {
                        const val = inp.value.trim();
                        if (val.startsWith('+') && val.length <= 5 && val.length >= 2) {
                            return val.replace('+', '');
                        }
                    }
                    return null;
                }""")
                if aol_page_prefix:
                    aol_page_prefix = str(aol_page_prefix).strip()
            except Exception:
                pass

            target_iso = COUNTRY_TO_ISO2.get(sms_country, "").upper()
            sms_prefix = phone_prefix or ""
            country_needs_change = aol_page_prefix and sms_prefix and aol_page_prefix != sms_prefix
            country_changed = not country_needs_change

            if country_needs_change:
                _log(f"AOL показывает +{aol_page_prefix}, SMS номер +{sms_prefix} — нужна смена")
                try:
                    changed = await page.evaluate(f"""() => {{
                        const inputs = document.querySelectorAll('input');
                        for (const inp of inputs) {{
                            const val = inp.value.trim();
                            if (val.startsWith('+') && val.length <= 5) {{
                                const setter = Object.getOwnPropertyDescriptor(
                                    window.HTMLInputElement.prototype, 'value').set;
                                setter.call(inp, '+{sms_prefix}');
                                inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                                inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                                return true;
                            }}
                        }}
                        return false;
                    }}""")
                    if changed:
                        country_changed = True
                        _log(f"Код страны сменён через JS: +{sms_prefix}")
                except Exception:
                    pass

                if not country_changed:
                    page_country = PREFIX_TO_SMS_COUNTRY.get(aol_page_prefix)
                    if page_country:
                        _log(f"⚠️ Не удалось сменить +{aol_page_prefix}→+{sms_prefix}. "
                             f"Отменяем номер и заказываем из {page_country}")
                        try:
                            await asyncio.to_thread(sms_provider.cancel_order, order_id)
                        except Exception:
                            pass
                        new_order = await order_sms_retry(
                            service="aol",
                            active_provider=sms_provider,
                            expanded_countries=[page_country] + [c for c in expanded_countries if c != page_country],
                            used_numbers={phone_number},
                            _log=_log,
                        )
                        if new_order:
                            phone_number = new_order["number"]
                            order_id = new_order["id"]
                            sms_country = new_order.get("country", page_country)
                            phone_prefix = PHONE_COUNTRY_MAP.get(sms_country)
                            local_number = phone_number.lstrip("+")
                            if phone_prefix and local_number.startswith(phone_prefix):
                                local_number = local_number[len(phone_prefix):]
                            _log(f"✅ Новый номер для +{aol_page_prefix}: {local_number}")
                        else:
                            _err(f"Не удалось заказать номер для +{aol_page_prefix}")
                            return None
                    else:
                        _log(f"⚠️ Не удалось сменить код, неизвестный prefix +{aol_page_prefix} — вводим полный номер")
                        local_number = f"{sms_prefix}{local_number}"

            # Human-like: read the page text first
            await random_mouse_move(page, steps=3)
            await _human_delay(3.0, 5.0)

            # Small scroll to see the full form
            await page.mouse.wheel(0, random.randint(30, 80))
            await _human_delay(0.8, 1.5)

            # Clear field first (in case AOL pre-filled something)
            try:
                await page.locator(phone_page_input).first.fill("")
                await _human_delay(0.3, 0.5)
            except Exception:
                pass

            # Fill the phone number with human typing
            await _human_fill(page, phone_page_input, local_number)
            _log(f"Ввели номер: {local_number}")
            await _human_delay(1.5, 3.0)

            # Human reads terms, looks at button before clicking
            await random_mouse_move(page, steps=2)
            await _human_delay(2.0, 4.0)

            # Click "Get code by text" button
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
                # ── RETRY LOOP: if AOL rejects the number, try up to 3 new numbers ──
                max_phone_retries = 3
                phone_accepted = False

                for phone_attempt in range(max_phone_retries):
                    if phone_attempt > 0:
                        _log(f"Попытка #{phone_attempt + 1} с новым номером...")

                    _log("Нажимаем 'Get code by text'...")
                    await _human_click(page, get_code_btn)
                    await _human_delay(4, 7)

                    # ── CRITICAL: AOL often shows reCAPTCHA AFTER clicking 'Get code' ──
                    for captcha_attempt in range(2):
                        captcha_solved = await _detect_and_solve_recaptcha(page, captcha_provider, _log)
                        if captcha_solved:
                            _log(f"CAPTCHA решена после 'Get code' (попытка {captcha_attempt + 1})")
                            await _human_delay(3, 6)
                            try:
                                resubmit = await _wait_for_any(page, [
                                    'button[type="submit"]',
                                    'button:has-text("Get code")',
                                    'button:has-text("Send code")',
                                    'button:has-text("Continue")',
                                    'button:has-text("Verify")',
                                ], timeout=3000)
                                if resubmit:
                                    await _human_click(page, resubmit)
                                    await _human_delay(4, 7)
                            except Exception:
                                pass
                        else:
                            break

                    # Check for phone rejection error on page
                    try:
                        page_text = await page.locator('body').inner_text()
                        rejection_phrases = [
                            "don't support this number",
                            "doesn't look right",
                            "not a valid phone",
                            "invalid phone",
                            "try another number",
                            "provide another one",
                            "unable to verify this number",
                            "не поддерживается",
                            "неверный номер",
                        ]
                        is_rejected = any(phrase.lower() in page_text.lower() for phrase in rejection_phrases)
                        if is_rejected:
                            matched = [p for p in rejection_phrases if p.lower() in page_text.lower()]
                            _log(f"AOL ошибка на странице: {matched}")
                    except Exception:
                        is_rejected = False

                    if not is_rejected:
                        curr = page.url
                        _log(f"После 'Get code': {curr}")
                        if 'challenge/fail' in curr or '/error' in curr:
                            captcha_on_fail = await _detect_and_solve_recaptcha(page, captcha_provider, _log)
                            if captcha_on_fail:
                                _log("CAPTCHA решена на странице challenge/fail, пытаемся снова...")
                                await _human_delay(3, 5)
                                curr2 = page.url
                                if 'challenge/fail' not in curr2 and '/error' not in curr2:
                                    phone_accepted = True
                                    break
                            _err("AOL заблокировал: challenge/fail")
                            await _debug_screenshot(page, "aol_blocked", _log)
                            try:
                                await asyncio.to_thread(sms_provider.cancel_number, order_id)
                            except Exception:
                                pass
                            return None

                        # Check if we ACTUALLY moved from the phone page
                        try:
                            phone_still_visible = await page.locator(phone_page_input).first.is_visible()
                        except Exception:
                            phone_still_visible = False

                        if phone_still_visible:
                            _log("⚠️ Форма телефона всё ещё видна — номер не принят, пробуем другой")
                            is_rejected = True
                        else:
                            phone_accepted = True
                            break

                    # Phone rejected — cancel old number and get a new one
                    _log(f"AOL отклонил номер {display_phone} — берём новый")
                    await _debug_screenshot(page, f"aol_phone_rejected_{phone_attempt}", _log)
                    try:
                        await asyncio.to_thread(sms_provider.cancel_number, order_id)
                    except Exception:
                        pass

                    # Order new number via shared retry function
                    new_order = await order_sms_retry(
                        service="aol",
                        active_provider=sms_provider,
                        expanded_countries=expanded_countries,
                        used_numbers={phone_number},
                        _log=_log,
                    )
                    if not new_order:
                        _err("SMS ошибка при получении нового номера")
                        return None

                    phone_number = new_order["number"]
                    order_id = new_order["id"]
                    sms_country = new_order.get("country", sms_country)
                    display_phone = phone_number if phone_number.startswith("+") else f"+{phone_number}"
                    _log(f"Новый номер: {display_phone} (страна: {sms_country})")

                    # Recalculate local number
                    phone_prefix = PHONE_COUNTRY_MAP.get(sms_country, phone_prefix)
                    local_number = phone_number.lstrip("+")
                    if phone_prefix and local_number.startswith(phone_prefix):
                        local_number = local_number[len(phone_prefix):]

                    # Clear phone field and fill with new number
                    try:
                        await page.locator(phone_page_input).first.fill("")
                        await _human_delay(0.3, 0.5)
                    except Exception:
                        pass
                    await _human_fill(page, phone_page_input, local_number)
                    _log(f"Ввели новый номер: {local_number}")
                    await _human_delay(1.5, 3.0)

                    # Re-find the button
                    get_code_btn = await _wait_for_any(page, [
                        'button:has-text("Get code by text")',
                        'button:has-text("code by text")',
                        'button[type="submit"]',
                    ], timeout=3000)
                    if not get_code_btn:
                        _err("Кнопка 'Get code' не найдена после смены номера")
                        return None

                if not phone_accepted:
                    _err(f"AOL отклонил {max_phone_retries} номеров подряд — прокси или SMS сервис")
                    return None
            else:
                _log("⚠️ Кнопка 'Get code by text' не найдена — пробуем Enter")
                await page.keyboard.press("Enter")
                await _human_delay(4, 7)
        else:
            _log("⚠️ Страница телефона не найдена — AOL мог не перейти на следующий шаг")
            await _debug_screenshot(page, "4_aol_no_phone_page", _log)
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

            _log("Ожидание SMS кода AOL...")
            _log(f"Страница: {page.url}")

            # Check if AOL redirected to challenge/fail BEFORE waiting for code
            sms_url = page.url
            if 'challenge/fail' in sms_url or '/error' in sms_url:
                _err(f"AOL перенаправил на challenge/fail после телефона: {sms_url}")
                await _debug_screenshot(page, "aol_challenge_after_phone", _log)
                captcha_solved = await _detect_and_solve_recaptcha(page, captcha_provider, _log)
                if not captcha_solved:
                    try:
                        await asyncio.to_thread(sms_provider.cancel_number, order_id)
                    except Exception:
                        pass
                    return None
                await _human_delay(3, 5)

            # Wait for code input fields (6-digit format, same as Yahoo)
            first_digit = await _wait_for_any(page, [
                'input#verify-code-0', 'input[aria-label="Code 1"]',
                'input[name="code"]', 'input[name="verificationCode"]',
                'input[name="verify_code"]', 'input[type="tel"][maxlength="1"]',
                'input[data-type="code"]', 'input.phone-code',
                'input[autocomplete="one-time-code"]',
            ], timeout=30000)

            if first_digit:
                _log(f"✅ Поле SMS кода найдено: {first_digit}")
            else:
                _log("⚠️ Поле SMS кода НЕ НАЙДЕНО — AOL не показал форму верификации!")
                _log(f"Текущий URL: {page.url}")
                await _debug_screenshot(page, "aol_no_sms_field", _log)
                try:
                    body_text = await page.locator('body').inner_text()
                    _log(f"Текст страницы: {body_text[:300]}")
                except Exception:
                    pass

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

        email = f"{username}@aol.com"
        final_url = page.url
        _log(f"Финальный URL: {final_url}")

        # ── CRITICAL: Verify registration actually succeeded ──
        registration_success = False
        try:
            success_indicators_url = [
                "mail.aol.com",
                "aol.com/welcome",
                "account/create/success",
                "/welcome",
                "/myaccount",
                "/manage_account",
            ]
            if any(ind in final_url.lower() for ind in success_indicators_url):
                registration_success = True
                _log("✅ URL подтверждает успешную регистрацию")

            if not registration_success:
                on_create = "/account/create" in final_url
                on_success = "/account/create/success" in final_url
                if not on_create or on_success:
                    registration_success = True
                    _log("✅ Покинули страницу регистрации — считаем успехом")

            # Final check: look for error indicators
            if registration_success:
                page_text = await page.locator('body').inner_text()
                fail_indicators = ["registration failed", "account could not be created", "ошибка регистрации"]
                if any(fi.lower() in page_text.lower() for fi in fail_indicators):
                    registration_success = False
                    _err("❌ Страница содержит индикаторы ошибки регистрации")
        except Exception as e:
            _log(f"Проверка успеха: ошибка ({e}), считаем успехом если URL сменился")
            on_create = "/account/create" in final_url
            on_success = "/account/create/success" in final_url
            if not on_create or on_success:
                registration_success = True

        if not registration_success:
            _err(f"❌ Регистрация НЕ подтверждена! URL: {final_url}")
            await _debug_screenshot(page, "aol_registration_not_confirmed", _log)
            return None

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
        export_account_to_file(account, {"sms_phone": display_phone})
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
