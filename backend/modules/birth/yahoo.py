"""
Leomail v3 — Yahoo Registration Engine
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

async def register_single_yahoo(
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
    """Register a single Yahoo account on desktop. Requires SMS."""
    if ACTIVE_PAGES is None:
        ACTIVE_PAGES = {}
    if BIRTH_CANCEL_EVENT is None:
        BIRTH_CANCEL_EVENT = threading.Event()
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
        n = getattr(thread_log, '_worker_id', 0) + 1 if thread_log else '?'
        logger.info(f"[Yahoo][Поток {n}] {msg}")
        if thread_log:
            thread_log.current_action = f"Поток {n}: {msg}"
            try:
                db.commit()
            except Exception:
                pass

    def _err(msg: str):
        n = getattr(thread_log, '_worker_id', 0) + 1 if thread_log else '?'
        logger.error(f"[Yahoo][Поток {n}] {msg}")
        if thread_log:
            thread_log.error_message = f"Поток {n}: {msg}"[:500]
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
            _log("Обнаружена страница 'Add your phone number'")

            if not sms_provider:
                _err("Yahoo требует SMS, но SMS провайдер не настроен")
                return None

            # ── PHONE_COUNTRY_MAP and reverse map ──
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
            # Reverse: phone prefix → SMS provider country code (e.g. "55" → "br")
            PREFIX_TO_SMS_COUNTRY = {}
            for sms_cc, prefix in PHONE_COUNTRY_MAP.items():
                if sms_cc not in PREFIX_TO_SMS_COUNTRY or len(prefix) > len(PREFIX_TO_SMS_COUNTRY.get(sms_cc, "")):
                    PREFIX_TO_SMS_COUNTRY[prefix] = sms_cc

            # ── STEP 1: Detect Yahoo's displayed country code from the page ──
            yahoo_page_prefix = None
            try:
                # Strategy A: Find input/element showing "+XX"
                detected = await page.evaluate("""() => {
                    // Check all inputs for a value like "+55"
                    const inputs = document.querySelectorAll('input');
                    for (const inp of inputs) {
                        const val = inp.value.trim();
                        if (val.startsWith('+') && val.length <= 5 && val.length >= 2) {
                            return val.replace('+', '');
                        }
                    }
                    // Check spans/divs that show country code text
                    const els = document.querySelectorAll('span, div, button, label');
                    for (const el of els) {
                        const text = el.textContent.trim();
                        // Match patterns like "+55" or "+381"
                        const match = text.match(/^\\+?(\\d{1,4})$/);
                        if (match && el.getBoundingClientRect().width < 100) {
                            return match[1];
                        }
                    }
                    // Check select elements for selected country code
                    const selects = document.querySelectorAll('select');
                    for (const sel of selects) {
                        const opt = sel.options[sel.selectedIndex];
                        if (opt) {
                            const m = opt.text.match(/\\+(\\d{1,4})/);
                            if (m) return m[1];
                        }
                    }
                    return null;
                }""")
                if detected:
                    yahoo_page_prefix = str(detected).strip()
                    _log(f"Yahoo показывает код страны: +{yahoo_page_prefix}")
            except Exception as e:
                _log(f"Не удалось определить код страны Yahoo: {e}")

            # ── STEP 2: Order SMS number from Yahoo's country (or fallback to configured) ──
            _log("Заказ номера для Yahoo SMS...")

            # Determine which country to order from
            yahoo_sms_country = None
            if yahoo_page_prefix:
                yahoo_sms_country = PREFIX_TO_SMS_COUNTRY.get(yahoo_page_prefix)
                if yahoo_sms_country:
                    _log(f"Yahoo требует страну +{yahoo_page_prefix} → SMS код: {yahoo_sms_country}")
                else:
                    _log(f"Код +{yahoo_page_prefix} не найден в маппинге, берём по конфигу")

            # Order from Yahoo's detected country FIRST, fallback to configured countries
            order = None
            if yahoo_sms_country:
                # Try ordering from Yahoo's exact country
                try:
                    _log(f"Заказываем номер из страны {yahoo_sms_country} (по коду Yahoo)...")
                    order = await asyncio.to_thread(sms_provider.order_number, "yahoo", yahoo_sms_country)
                    if "error" in order:
                        _log(f"Нет номеров в {yahoo_sms_country}: {order.get('error', '')}, пробуем другие страны...")
                        order = None
                except Exception as e:
                    _log(f"Ошибка заказа из {yahoo_sms_country}: {e}")
                    order = None

            if not order:
                # Fallback: use configured countries
                _countries = getattr(sms_provider, '_sms_countries', None)
                _blacklist = getattr(sms_provider, '_country_blacklist', None)
                if _countries and hasattr(sms_provider, 'order_number_from_countries'):
                    order = await asyncio.to_thread(sms_provider.order_number_from_countries, "yahoo", _countries, _blacklist)
                else:
                    order = await asyncio.to_thread(sms_provider.order_number, "yahoo", "auto")

            if not order or "error" in order:
                _err(f"SMS ошибка: {order.get('error', 'no order') if order else 'Failed to order'}")
                return None

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

            # ── STEP 4: Change Yahoo's country code IF it doesn't match ──
            target_iso = COUNTRY_TO_ISO2.get(sms_country, "").upper()
            sms_prefix = phone_prefix or ""
            country_needs_change = yahoo_page_prefix and sms_prefix and yahoo_page_prefix != sms_prefix
            country_changed = not country_needs_change  # Already correct = no change needed

            if country_needs_change:
                _log(f"Yahoo показывает +{yahoo_page_prefix}, SMS номер +{sms_prefix} — нужна смена")
                try:
                    # Try JS to change the country code input value
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
                    _log(f"Не удалось сменить код — вводим полный номер +{sms_prefix}{local_number}")
                    local_number = f"{sms_prefix}{local_number}"

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

            # Human reads terms, looks at button before clicking
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
                # ── RETRY LOOP: if Yahoo rejects the number, try up to 3 new numbers ──
                max_phone_retries = 3
                phone_accepted = False

                for phone_attempt in range(max_phone_retries):
                    if phone_attempt > 0:
                        _log(f"Попытка #{phone_attempt + 1} с новым номером...")

                    _log("Нажимаем 'Get code by text'...")
                    await _human_click(page, get_code_btn)
                    await _human_delay(4, 7)

                    # ── CRITICAL: Yahoo often shows reCAPTCHA AFTER clicking 'Get code' ──
                    # We must detect and solve it BEFORE checking for challenge/fail!
                    for captcha_attempt in range(2):
                        captcha_solved = await _detect_and_solve_recaptcha(page, captcha_provider, _log)
                        if captcha_solved:
                            _log(f"CAPTCHA решена после 'Get code' (попытка {captcha_attempt + 1})")
                            await _human_delay(3, 6)  # Wait for Yahoo to process
                            # Re-click submit if still on same page
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
                            "не поддерживается",
                            "неверный номер",
                        ]
                        is_rejected = any(phrase.lower() in page_text.lower() for phrase in rejection_phrases)
                    except Exception:
                        is_rejected = False

                    if not is_rejected:
                        # Also check URL for challenge/fail
                        curr = page.url
                        _log(f"После 'Get code': {curr}")
                        if 'challenge/fail' in curr or '/error' in curr:
                            # One more attempt: maybe there's a captcha on this page too
                            captcha_on_fail = await _detect_and_solve_recaptcha(page, captcha_provider, _log)
                            if captcha_on_fail:
                                _log("CAPTCHA решена на странице challenge/fail, пытаемся снова...")
                                await _human_delay(3, 5)
                                # Check if we moved away from the fail page
                                curr2 = page.url
                                if 'challenge/fail' not in curr2 and '/error' not in curr2:
                                    phone_accepted = True
                                    break
                            _err("Yahoo заблокировал: challenge/fail")
                            await _debug_screenshot(page, "yahoo_blocked", _log)
                            try:
                                await asyncio.to_thread(sms_provider.cancel_number, order_id)
                            except Exception:
                                pass
                            return None
                        phone_accepted = True
                        break

                    # Phone rejected — cancel old number and get a new one
                    _log(f"Yahoo отклонил номер {display_phone} — берём новый")
                    await _debug_screenshot(page, f"yahoo_phone_rejected_{phone_attempt}", _log)
                    try:
                        await asyncio.to_thread(sms_provider.cancel_number, order_id)
                    except Exception:
                        pass

                    # Order new number
                    if _countries and hasattr(sms_provider, 'order_number_from_countries'):
                        new_order = await asyncio.to_thread(sms_provider.order_number_from_countries, "yahoo", _countries, _blacklist)
                    else:
                        new_order = await asyncio.to_thread(sms_provider.order_number, "yahoo", "auto")
                    if "error" in new_order:
                        _err(f"SMS ошибка при получении нового номера: {new_order['error']}")
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

                    # Re-find the button (might change state)
                    get_code_btn = await _wait_for_any(page, [
                        'button:has-text("Get code by text")',
                        'button:has-text("code by text")',
                        'button[type="submit"]',
                    ], timeout=3000)
                    if not get_code_btn:
                        _err("Кнопка 'Get code' не найдена после смены номера")
                        return None

                if not phone_accepted:
                    _err(f"Yahoo отклонил {max_phone_retries} номеров подряд — прокси или SMS сервис")
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
