"""
Leomail v3 — Outlook/Hotmail Registration Engine
"""
import asyncio
import random
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
)


async def register_single_outlook(
    browser_manager: BrowserManager,
    proxy: Proxy | None,
    device_type: str,
    name_pool: list,
    captcha_provider: CaptchaProvider | None,
    db: Session,
    thread_log: ThreadLog | None = None,
    domain: str = "outlook.com",
    ACTIVE_PAGES: dict = None,
) -> Account | None:
    """Register a single Outlook/Hotmail account with human-like behavior."""
    if ACTIVE_PAGES is None:
        ACTIVE_PAGES = {}
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
        tid = thread_log.id if thread_log else '?'
        logger.info(f"[Outlook][#{tid}] {msg}")
        if thread_log:
            thread_log.current_action = f"#{thread_log.id} {msg}"
            try:
                db.commit()
            except Exception:
                pass

    def _err(msg: str):
        tid = thread_log.id if thread_log else '?'
        logger.error(f"[Outlook][#{tid}] {msg}")
        if thread_log:
            thread_log.error_message = f"#{thread_log.id} {msg}"[:500]
            try:
                db.commit()
            except Exception:
                pass

    thread_id = thread_log.id if thread_log else 0

    try:
        page = await context.new_page()
        ACTIVE_PAGES[thread_id] = {"page": page, "context": context}

        _log("Прогрев сессии...")
        try:
            await pre_registration_warmup(page)
        except Exception as warmup_e:
            logger.debug(f"Warmup error (proxy may be dead): {warmup_e}")

        warmup_url = page.url or ""
        if "chrome-error" in warmup_url or "about:blank" == warmup_url:
            _log("⚠️ Прокси не работает, прогрев не удался")

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

        current_url = page.url or ""
        if "chrome-error" in current_url or "about:blank" == current_url:
            _err(f"🔴 Прокси МЁРТВ — страница не загрузилась (URL: {current_url})")
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

        email_selectors = [
            'input[name="MemberName"]', '#MemberName', '#iMemberName',
            'input[name="Email"]',
            'input[type="email"]', 'input[type="text"][name="MemberName"]',
            'input[aria-label*="email"]', 'input[aria-label*="Email"]',
            'input[placeholder*="email"]', 'input[placeholder*="Email"]',
            'input[id*="floatingLabel"]',
        ]
        _log(f"Ввод email: {email}")
        found = await _wait_and_find(page, email_selectors, "email", username, _log, _err, timeout=20000)
        if not found:
            return None

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

        if got_new_email_mode and domain != "outlook.com":
            domain_sel = await _wait_for_any(page, [
                'select#LiveDomainBoxList', '#LiveDomainBoxList',
                'select[name="DomainList"]', 'select[aria-label*="domain"]',
            ], timeout=5000)
            if domain_sel:
                _log(f"Выбор домена: @{domain}")
                await page.locator(domain_sel).first.select_option(domain)
                await _human_delay(0.5, 1)

        next_selectors = ['#iSignupAction', 'input[type="submit"]', 'button[type="submit"]']
        next_btn = await _wait_for_any(page, next_selectors, timeout=5000)
        if next_btn:
            await page.locator(next_btn).first.click()
        else:
            await page.keyboard.press("Enter")

        await _human_delay(3, 6)

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

        _log("Ввод даты рождения...")
        await _human_delay(1, 2)
        await _step_screenshot(page, "before_birthday", username)

        month_names = [
            "", "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        month_name = month_names[birthday.month] if 1 <= birthday.month <= 12 else str(birthday.month)

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

        month_ok = await _fluent_combobox_select(page, [
            '#BirthMonthDropdown',
            'button[name="BirthMonth"]',
            'button[aria-label*="irth month"]',
            'button[aria-label*="есяц"]',
        ], month_name, "Month", _log, timeout=10000)
        if not month_ok:
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

        next_btn_bday = await _wait_for_any(page, next_selectors, timeout=3000)
        if next_btn_bday:
            await page.locator(next_btn_bday).first.click()
        else:
            await page.keyboard.press("Enter")
        await _human_delay(2, 4)

        _log(f"Ввод имени: {first_name} {last_name}")
        fn_selectors = [
            '#firstNameInput',
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
                '#lastNameInput',
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

        _log("Проверка CAPTCHA...")
        captcha_frame = page.locator('iframe[title*="captcha"], iframe[title*="Verification"], iframe[title*="Human"], iframe[src*="funcaptcha"], iframe[src*="hsprotect"], #enforcementFrame')
        if await captcha_frame.count() > 0:
            from ...services.captcha_provider import get_twocaptcha_provider
            tc_provider = get_twocaptcha_provider()
            if tc_provider:
                _log("🔐 FunCaptcha обнаружена! Решаем через 2Captcha...")
                try:
                    site_key = "B7D8911C-5CC8-A9A3-35B0-554ACEE604DA"
                    surl = "https://client-api.arkoselabs.com"
                    token = await asyncio.wait_for(
                        asyncio.to_thread(tc_provider.solve_funcaptcha, site_key, page.url, surl),
                        timeout=180,
                    )
                    if token:
                        _log("✅ FunCaptcha решена! Вставляем токен...")
                        await page.evaluate(f"""(() => {{
                            try {{
                                var ef = document.getElementById("enforcementFrame");
                                if (ef && ef.contentWindow) {{
                                    ef.contentWindow.postMessage(JSON.stringify({{token: "{token}"}}), "*");
                                }}
                            }} catch(e) {{}}
                            try {{
                                var inputs = document.querySelectorAll('input[name*="fc-token"], input[name*="verification"]');
                                inputs.forEach(i => {{ i.value = "{token}"; }});
                            }} catch(e) {{}}
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

        _log("Проверка результата...")
        await _human_delay(3, 5)
        final_url = page.url.lower()
        _log(f"Финальный URL: {final_url}")

        try:
            session_path = await browser_manager.save_session(context, 0)
        except Exception as se:
            logger.warning(f"[Birth] Session save warning: {se}")
            session_path = None

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
        ACTIVE_PAGES.pop(thread_id, None)
        try:
            await context.close()
        except Exception:
            pass
