"""
Leomail v3 — Outlook/Hotmail Registration Engine (with Vision CV)
Upgraded: human_fill, BIRTH_CANCEL_EVENT, better error handling, proxy detection.
"""
import asyncio
import random
import threading
from loguru import logger
from sqlalchemy.orm import Session

from ...models import Proxy, ProxyStatus, Account, ThreadLog
from ...services.captcha_provider import CaptchaProvider, get_captcha_chain
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
    export_account_to_file,
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
    BIRTH_CANCEL_EVENT: threading.Event = None,
) -> Account | None:
    """Register a single Outlook/Hotmail account with human-like behavior."""
    if ACTIVE_PAGES is None:
        ACTIVE_PAGES = {}
    if BIRTH_CANCEL_EVENT is None:
        BIRTH_CANCEL_EVENT = threading.Event()
    if not name_pool:
        logger.error("[Outlook] ❌ Нет имён! Загрузите пакет имён перед регистрацией.")
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
        n = getattr(thread_log, '_worker_id', 0) + 1 if thread_log else '?'
        logger.info(f"[Outlook][Поток {n}] {msg}")
        if thread_log:
            thread_log.current_action = f"Поток {n}: {msg}"
            try:
                db.commit()
            except Exception:
                pass

    def _err(msg: str):
        n = getattr(thread_log, '_worker_id', 0) + 1 if thread_log else '?'
        logger.error(f"[Outlook][Поток {n}] {msg}")
        if thread_log:
            thread_log.error_message = f"Поток {n}: {msg}"[:500]
            try:
                db.commit()
            except Exception:
                pass

    thread_id = thread_log.id if thread_log else 0

    # ── Initialize Vision Engine ──
    vision = None
    try:
        from ..vision import VisionEngine
        vision = VisionEngine("outlook", debug=True)
        _log("👁️ Vision Engine активен")
    except Exception as ve:
        logger.debug(f"[Outlook] Vision not available: {ve}")

    try:
        page = await context.new_page()
        ACTIVE_PAGES[thread_id] = {"page": page, "context": context}

        # Fast warmup — just a quick Google visit (2-3s instead of 15-30s)
        _log("Быстрый прогрев сессии...")
        try:
            await page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=15000)
            await _human_delay(1, 2)
            await random_mouse_move(page, steps=2)
        except Exception as warmup_e:
            logger.debug(f"Warmup error (proxy may be dead): {warmup_e}")

        warmup_url = page.url or ""
        if "chrome-error" in warmup_url or "about:blank" == warmup_url:
            _log("⚠️ Прокси не работает, прогрев не удался")

        # ── Step 1: Navigate to Outlook signup ──
        _log("Открытие страницы регистрации...")
        try:
            await page.goto(
                "https://signup.live.com/signup",
                wait_until="domcontentloaded",
                timeout=60000,
            )
        except Exception as nav_e:
            logger.warning(f"[Outlook] Navigation error: {nav_e}")

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
                    logger.warning(f"Proxy marked DEAD during birth: {proxy.host}:{proxy.port}")
                except Exception:
                    pass
            return None

        # Check for error/block pages
        if "error" in current_url.split("?")[0].lower() or "blocked" in current_url.lower():
            _err(f"🔴 MS вернул страницу ошибки (URL: {current_url})")
            return None

        await random_mouse_move(page, steps=3)
        _log(f"Страница: {page.url}")

        # ── Step 2: Handle "Get a new email address" link ──
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

        # ── Step 3: Enter email/username ──
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

        await _human_fill(page, found, text_to_enter)
        await _human_delay(0.8, 1.5)

        # Select domain if needed
        if got_new_email_mode and domain != "outlook.com":
            domain_sel = await _wait_for_any(page, [
                'select#LiveDomainBoxList', '#LiveDomainBoxList',
                'select[name="DomainList"]', 'select[aria-label*="domain"]',
            ], timeout=5000)
            if domain_sel:
                _log(f"Выбор домена: @{domain}")
                await page.locator(domain_sel).first.select_option(domain)
                await _human_delay(0.5, 1)

        # Click Next
        next_selectors = ['#iSignupAction', 'input[type="submit"]', 'button[type="submit"]']
        next_btn = await _wait_for_any(page, next_selectors, timeout=5000)
        if next_btn:
            await _human_click(page, next_btn)
        else:
            await page.keyboard.press("Enter")

        await _human_delay(3, 6)

        # ── Email-taken retry (up to 3 attempts) ──
        for email_retry in range(3):
            err_text = await _check_error_on_page(page)
            if err_text:
                old_username = username
                username = generate_username(first_name, last_name)
                email = f"{username}@{domain}"
                _log(f"⚠️ Email '{old_username}@{domain}' занят: {err_text}. Пробуем: {email}")
                text_to_enter = username if got_new_email_mode else email
                found2 = await _wait_for_any(page, email_selectors, timeout=5000)
                if found2:
                    await page.locator(found2).first.fill("")
                    await _human_fill(page, found2, text_to_enter)
                await _human_delay(0.5, 1)
                next_retry = await _wait_for_any(page, next_selectors, timeout=3000)
                if next_retry:
                    await _human_click(page, next_retry)
                else:
                    await page.keyboard.press("Enter")
                await _human_delay(3, 5)
            else:
                break
        else:
            _err(f"MS отклонил 3 email подряд")
            return None

        # ── Step 4: Password ──
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

        await _human_fill(page, found, password)
        await _human_delay(0.5, 1.2)

        next_btn2 = await _wait_for_any(page, next_selectors, timeout=3000)
        if next_btn2:
            await _human_click(page, next_btn2)
        else:
            await page.keyboard.press("Enter")
        await _human_delay(2, 4)

        # ── Step 5: Birthday (Country + Month + Day + Year) ──
        _log("Ввод даты рождения...")
        await _human_delay(1, 2)
        await _step_screenshot(page, "before_birthday", username)

        month_names = [
            "", "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        month_name = month_names[birthday.month] if 1 <= birthday.month <= 12 else str(birthday.month)

        # Country selection — use GEO profile from proxy if available
        from ...services.geo_resolver import build_geo_profile, resolve_proxy_geo
        proxy_geo = resolve_proxy_geo(proxy) if proxy else None
        geo_profile = build_geo_profile(proxy_geo) if proxy_geo else None

        # Map country code to MS registration name
        _MS_COUNTRY_NAMES = {
            "US": "United States", "GB": "United Kingdom", "CA": "Canada",
            "AU": "Australia", "DE": "Germany", "FR": "France",
            "NL": "Netherlands", "SE": "Sweden", "IE": "Ireland",
            "NZ": "New Zealand", "AT": "Austria", "BR": "Brazil",
            "MX": "Mexico", "ES": "Spain", "PL": "Poland",
            "CZ": "Czechia", "RO": "Romania", "TR": "Turkey",
        }
        if geo_profile and geo_profile["country"] in _MS_COUNTRY_NAMES:
            chosen_country = _MS_COUNTRY_NAMES[geo_profile["country"]]
        else:
            country_pool = [
                "United States", "United Kingdom", "Canada", "Australia",
                "Germany", "France", "Netherlands", "Sweden",
            ]
            chosen_country = random.choice(country_pool)
        _log(f"Выбор страны: {chosen_country} (GEO: {proxy_geo or 'auto'})")
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

        # Month
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

        # Day
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

        # Year
        year_sels = [
            'input[name="BirthYear"]', '#BirthYear',
            'input[aria-label*="irth year"]', 'input[aria-label*="од рожд"]',
            'input[type="number"]',
        ]
        year_sel = await _wait_for_any(page, year_sels, timeout=5000)
        if year_sel:
            await _human_fill(page, year_sel, str(birthday.year))
            _log(f"Year: {birthday.year}")
        else:
            _log("⚠️ Year field не найден")
        await _human_delay(0.5, 1)

        # Human scrolls and reviews before submit
        await page.mouse.wheel(0, random.randint(50, 150))
        await _human_delay(0.8, 1.5)

        next_btn_bday = await _wait_for_any(page, next_selectors, timeout=3000)
        if next_btn_bday:
            await _human_click(page, next_btn_bday)
        else:
            await page.keyboard.press("Enter")
        await _human_delay(2, 4)

        # ── Step 6: First/Last Name ──
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
            await _human_fill(page, name_found, first_name)
            await _human_delay(0.8, 1.5)

            ln_selectors = [
                '#lastNameInput',
                'input[name="LastName"]', '#LastName', '#iLastName',
                'input[placeholder*="фамил"]', 'input[placeholder*="ast"]',
                'input[aria-label*="ast name"]', 'input[aria-label*="фам"]',
            ]
            found_ln = await _wait_for_any(page, ln_selectors, timeout=5000)
            if found_ln:
                await _human_fill(page, found_ln, last_name)
            await _human_delay(0.5, 1)

            # Human scroll + review
            await random_mouse_move(page, steps=2)
            await _human_delay(1.0, 2.0)

            next_btn_name = await _wait_for_any(page, next_selectors, timeout=3000)
            if next_btn_name:
                await _human_click(page, next_btn_name)
            else:
                await page.keyboard.press("Enter")
            await _human_delay(3, 6)
        else:
            _log("⚠️ Страница имени не найдена — возможно уже на CAPTCHA")

        # ── Step 7: FunCaptcha ──
        _log("Проверка CAPTCHA...")
        captcha_frame = page.locator('iframe[title*="captcha"], iframe[title*="Verification"], iframe[title*="Human"], iframe[src*="funcaptcha"], iframe[src*="hsprotect"], #enforcementFrame')

        # Wait a bit for captcha to appear (MS sometimes delays it)
        await _human_delay(2, 4)

        if await captcha_frame.count() > 0:
            captcha_chain = get_captcha_chain()
            if captcha_chain.providers:
                _log("🔐 FunCaptcha обнаружена! Решаем через CaptchaChain...")
                try:
                    # Dynamic site key extraction from iframe
                    site_key = "B7D8911C-5CC8-A9A3-35B0-554ACEE604DA"  # MS default
                    surl = "https://client-api.arkoselabs.com"
                    try:
                        extracted_key = await page.evaluate("""(() => {
                            // Try iframe src
                            const frames = document.querySelectorAll('iframe[src*="funcaptcha"], iframe[src*="arkoselabs"]');
                            for (const f of frames) {
                                const m = f.src.match(/pk=([A-F0-9-]+)/i);
                                if (m) return m[1];
                            }
                            // Try data attributes
                            const el = document.querySelector('[data-pkey], [data-public-key]');
                            if (el) return el.getAttribute('data-pkey') || el.getAttribute('data-public-key');
                            // Try enforcement config
                            if (window.enforcement && window.enforcement.publicKey) return window.enforcement.publicKey;
                            return null;
                        })()""")
                        if extracted_key:
                            site_key = extracted_key
                            _log(f"Извлечён ключ FunCaptcha: {site_key[:20]}...")
                    except Exception:
                        _log("Используем дефолтный MS FunCaptcha ключ")

                    # Solve via chain (tries all configured providers)
                    token = await asyncio.wait_for(
                        asyncio.to_thread(
                            captcha_chain.solve,
                            "funcaptcha",
                            public_key=site_key,
                            page_url=page.url,
                            surl=surl,
                        ),
                        timeout=180,
                    )
                    if token:
                        _log("✅ FunCaptcha решена! Вставляем токен...")
                        # Enhanced token injection — 4 strategies
                        await page.evaluate(f"""(() => {{
                            const token = "{token}";
                            // Strategy 1: postMessage to enforcement iframe
                            try {{
                                var ef = document.getElementById("enforcementFrame");
                                if (ef && ef.contentWindow) {{
                                    ef.contentWindow.postMessage(JSON.stringify({{token: token}}), "*");
                                }}
                            }} catch(e) {{}}
                            // Strategy 2: Set hidden input values
                            try {{
                                document.querySelectorAll('input[name*="fc-token"], input[name*="verification"], input[name*="FC"]')
                                    .forEach(i => {{ i.value = token; i.dispatchEvent(new Event('change', {{bubbles: true}})); }});
                            }} catch(e) {{}}
                            // Strategy 3: Callback function
                            try {{ if (window.funcaptchaCallback) window.funcaptchaCallback(token); }} catch(e) {{}}
                            try {{ if (window.ArkoseEnforcement) window.ArkoseEnforcement.setConfig({{onCompleted: token}}); }} catch(e) {{}}
                            // Strategy 4: Trigger form submission signal
                            try {{
                                var evt = new CustomEvent('arkose-completed', {{detail: {{token: token}}}});
                                document.dispatchEvent(evt);
                            }} catch(e) {{}}
                        }})()""")
                        await _human_delay(3, 6)
                        _log("Токен вставлен, ожидание...")

                        # After token injection, try clicking any submit/next button
                        post_captcha_btn = await _wait_for_any(page, [
                            '#iSignupAction', 'button[type="submit"]', 'input[type="submit"]',
                        ], timeout=5000)
                        if post_captcha_btn:
                            await _human_click(page, post_captcha_btn)
                            await _human_delay(3, 6)
                    else:
                        _err("❌ CaptchaChain: все провайдеры не смогли решить FunCaptcha")
                        return None
                except asyncio.TimeoutError:
                    _err("❌ Таймаут решения FunCaptcha (180с)")
                    return None
                except Exception as e:
                    _err(f"CAPTCHA ошибка: {str(e)[:200]}")
                    return None
            else:
                _err("FunCaptcha нужна, но нет сконфигурированных CAPTCHA провайдеров!")
                return None
        else:
            _log("Капча не обнаружена — продолжаем")

        # ── Step 8: Post-captcha — check for additional prompts ──
        # MS may show "Stay signed in?" or other prompts
        await _human_delay(2, 4)

        # Handle "Stay signed in?" prompt
        stay_signed_in = await _wait_for_any(page, [
            '#KmsiBanner', '#acceptButton', 'button:has-text("Yes")',
            'input[value="Yes"]', '#idSIButton9',
        ], timeout=5000)
        if stay_signed_in:
            _log("Нажимаем 'Да' на 'Stay signed in?'")
            await _human_click(page, stay_signed_in)
            await _human_delay(3, 5)

        # Handle "Get the Outlook app" or similar promo pages
        skip_promo = await _wait_for_any(page, [
            'button:has-text("Skip")', 'a:has-text("Skip")',
            'button:has-text("Пропустить")', 'a:has-text("Пропустить")',
            'button:has-text("No thanks")', 'a:has-text("No thanks")',
            'button:has-text("Maybe later")', '#declineButton',
        ], timeout=3000)
        if skip_promo:
            _log("Пропускаем промо-страницу...")
            await _human_click(page, skip_promo)
            await _human_delay(2, 4)

        # ── Step 9: Verify registration succeeded ──
        _log("Проверка результата...")
        await _human_delay(2, 4)
        final_url = page.url.lower()
        _log(f"Финальный URL: {final_url}")

        registration_success = False
        try:
            success_indicators = [
                "outlook.live.com", "signup.live.com/signup?sru",
                "/MailSetup", "account.microsoft.com",
                "outlook.office.com", "outlook.office365.com",
            ]
            if any(ind in final_url for ind in success_indicators):
                registration_success = True
                _log("✅ URL подтверждает успешную регистрацию")
            elif "signup.live.com" not in final_url:
                # Left the signup page = likely success
                registration_success = True
                _log("✅ Покинули страницу регистрации")
            else:
                # Still on signup — check for specific failure indicators
                page_text = await page.locator('body').inner_text()
                fail_indicators = ["something went wrong", "couldn't create", "error", "blocked"]
                if any(fi.lower() in page_text.lower() for fi in fail_indicators):
                    _err(f"❌ Страница содержит индикаторы ошибки")
                    await _debug_screenshot(page, "outlook_error_on_page", _log)
                else:
                    # On signup page but no error — probably captcha pending
                    _log("⚠️ Всё ещё на signup.live.com, но ошибок нет")
                    await _debug_screenshot(page, "outlook_still_on_signup", _log)
        except Exception as e:
            _log(f"Проверка успеха: ошибка ({e}), считаем успехом если URL сменился")
            if "signup.live.com" not in final_url:
                registration_success = True

        if not registration_success:
            _err(f"❌ Регистрация НЕ подтверждена! URL: {final_url}")
            await _debug_screenshot(page, "outlook_not_confirmed", _log)
            return None

        # ── Save session and create account ──
        try:
            session_path = await browser_manager.save_session(context, 0)
        except Exception as se:
            logger.warning(f"[Outlook] Session save warning: {se}")
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

        logger.info(f"✅ Outlook registered: {email}")
        export_account_to_file(account)
        return account

    except Exception as e:
        logger.error(f"❌ Outlook registration failed: {e}", exc_info=True)
        _err(str(e)[:500])
        return None
    finally:
        ACTIVE_PAGES.pop(thread_id, None)
        try:
            await context.close()
        except Exception:
            pass
