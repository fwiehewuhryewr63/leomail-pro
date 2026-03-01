"""
Leomail v3 — ProtonMail Registration Engine
Registers proton.me / protonmail.com accounts.
Flow: account.proton.me/signup → username → password → hCaptcha → (optional recovery email)
No phone verification required for basic registration.
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
    wait_for_any as _wait_for_any,
    step_screenshot as _step_screenshot,
    wait_and_find as _wait_and_find,
    debug_screenshot as _debug_screenshot,
    export_account_to_file,
)


async def register_single_protonmail(
    browser_manager: BrowserManager,
    proxy: Proxy | None,
    device_type: str,
    name_pool: list,
    captcha_provider: CaptchaProvider | None,
    db: Session,
    thread_log: ThreadLog | None = None,
    ACTIVE_PAGES: dict = None,
    BIRTH_CANCEL_EVENT: threading.Event = None,
) -> Account | None:
    """Register a single ProtonMail account with human-like behavior."""
    if ACTIVE_PAGES is None:
        ACTIVE_PAGES = {}
    if BIRTH_CANCEL_EVENT is None:
        BIRTH_CANCEL_EVENT = threading.Event()
    if not name_pool:
        logger.error("[ProtonMail] ❌ Нет имён! Загрузите пакет имён перед регистрацией.")
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
    # ProtonMail username — letters, numbers, dots, dashes, underscores
    username = username.replace("_", ".").lower()
    email = f"{username}@proton.me"

    context = await browser_manager.create_context(
        proxy=proxy,
        device_type=device_type,
        geo=None,
    )

    def _log(msg: str):
        n = getattr(thread_log, '_worker_id', 0) + 1 if thread_log else '?'
        logger.info(f"[ProtonMail][Поток {n}] {msg}")
        if thread_log:
            thread_log.current_action = f"Поток {n}: {msg}"
            try:
                db.commit()
            except Exception:
                pass

    def _err(msg: str):
        n = getattr(thread_log, '_worker_id', 0) + 1 if thread_log else '?'
        logger.error(f"[ProtonMail][Поток {n}] {msg}")
        if thread_log:
            thread_log.error_message = f"Поток {n}: {msg}"[:500]
            try:
                db.commit()
            except Exception:
                pass

    thread_id = thread_log.id if thread_log else 0

    try:
        page = await context.new_page()
        ACTIVE_PAGES[thread_id] = page

        # ── Step 1: Navigate to signup ──
        _log("Переход на страницу регистрации...")
        await page.goto("https://account.proton.me/signup", wait_until="domcontentloaded", timeout=60000)
        await _human_delay(2.0, 4.0)
        await _debug_screenshot(page, "proton_signup_page", _log)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        # ── Step 2: Select Free plan ──
        _log("Выбор бесплатного плана...")
        # Try to find and click Free plan button
        free_plan_selectors = [
            'button:has-text("Get Proton Free")',
            'button:has-text("Free")',
            '[data-testid="select-free"]',
            'a[href*="free"]',
        ]
        for sel in free_plan_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=3000):
                    await btn.click()
                    _log("Выбран бесплатный план")
                    break
            except Exception:
                continue
        await _human_delay(2.0, 3.0)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        # ── Step 3: Enter username ──
        _log(f"Ввод имени пользователя: {username}")
        username_selectors = [
            '#email',
            'input[name="email"]',
            'input[id="email"]',
            'input[placeholder*="username"]',
            'input[data-testid="signup:email"]',
        ]
        username_filled = False
        for sel in username_selectors:
            try:
                inp = page.locator(sel).first
                if await inp.is_visible(timeout=3000):
                    await _human_fill(page, sel, username)
                    username_filled = True
                    _log(f"Username введён: {username}")
                    break
            except Exception:
                continue

        if not username_filled:
            _err("Не найдено поле username")
            await _debug_screenshot(page, "proton_no_username_field", _log)
            return None

        await _human_delay(1.0, 2.0)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        # ── Step 4: Enter password ──
        _log("Ввод пароля...")
        password_selectors = [
            '#password',
            'input[name="password"]',
            'input[type="password"]',
            'input[data-testid="signup:password"]',
        ]
        for sel in password_selectors:
            try:
                inp = page.locator(sel).first
                if await inp.is_visible(timeout=3000):
                    await _human_fill(page, sel, password)
                    _log("Пароль введён")
                    break
            except Exception:
                continue

        await _human_delay(0.5, 1.5)

        # Confirm password
        confirm_selectors = [
            '#repeat-password',
            'input[name="confirmPassword"]',
            'input[data-testid="signup:confirm-password"]',
        ]
        for sel in confirm_selectors:
            try:
                inp = page.locator(sel).first
                if await inp.is_visible(timeout=3000):
                    await _human_fill(page, sel, password)
                    _log("Пароль подтверждён")
                    break
            except Exception:
                continue

        await _human_delay(1.0, 2.0)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        # ── Step 5: Submit form / Create account button ──
        _log("Нажатие кнопки создания аккаунта...")
        submit_selectors = [
            'button[type="submit"]',
            'button:has-text("Create account")',
            'button:has-text("Создать аккаунт")',
            'button:has-text("Next")',
            'button:has-text("Далее")',
        ]
        for sel in submit_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=3000):
                    await btn.click()
                    _log("Форма отправлена")
                    break
            except Exception:
                continue

        await _human_delay(3.0, 5.0)
        await _debug_screenshot(page, "proton_after_submit", _log)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        # ── Step 6: Handle hCaptcha via CaptchaChain ──
        _log("Проверка hCaptcha...")
        try:
            hcaptcha_frame = page.frame_locator('iframe[src*="hcaptcha"]')
            checkbox = hcaptcha_frame.locator('#checkbox')
            if await checkbox.is_visible(timeout=5000):
                _log("hCaptcha обнаружена — решение через CaptchaChain...")
                captcha_chain = get_captcha_chain()
                if captcha_chain.providers:
                    try:
                        # Extract sitekey from iframe
                        site_key = await page.evaluate("""
                            () => {
                                const iframe = document.querySelector('iframe[src*="hcaptcha"]');
                                if (iframe) {
                                    const url = new URL(iframe.src);
                                    return url.searchParams.get('sitekey') || '';
                                }
                                const el = document.querySelector('[data-sitekey]');
                                if (el) return el.getAttribute('data-sitekey');
                                return '';
                            }
                        """)
                        if site_key:
                            _log(f"hCaptcha sitekey: {site_key[:20]}...")
                            solution = await asyncio.wait_for(
                                asyncio.to_thread(
                                    captcha_chain.solve,
                                    "hcaptcha",
                                    sitekey=site_key,
                                    url=page.url,
                                ),
                                timeout=120,
                            )
                            if solution:
                                # Enhanced token injection — 3 strategies
                                await page.evaluate(f"""
                                    (() => {{
                                        const token = "{solution}";
                                        // Strategy 1: Hidden response fields
                                        document.querySelectorAll('[name="h-captcha-response"], [name="g-recaptcha-response"]')
                                            .forEach(el => {{ el.value = token; }});
                                        // Strategy 2: textarea (Proton uses this)
                                        document.querySelectorAll('textarea[name="h-captcha-response"]')
                                            .forEach(el => {{ el.value = token; el.dispatchEvent(new Event('input', {{bubbles: true}})); }});
                                        // Strategy 3: hcaptcha callback
                                        try {{ if (window.hcaptcha) window.hcaptcha.execute(); }} catch(e) {{}}
                                    }})()
                                """)
                                _log("hCaptcha решена через CaptchaChain ✅")
                                await _human_delay(2.0, 4.0)
                                
                                # Re-submit form after captcha
                                for sel in ['button[type="submit"]', 'button:has-text("Create account")']:
                                    try:
                                        btn = page.locator(sel).first
                                        if await btn.is_visible(timeout=2000):
                                            await btn.click()
                                            break
                                    except Exception:
                                        continue
                                await _human_delay(3.0, 5.0)
                            else:
                                _err("hCaptcha: CaptchaChain не смог решить")
                        else:
                            _err("hCaptcha: не найден sitekey")
                    except asyncio.TimeoutError:
                        _err("hCaptcha: таймаут 120с")
                    except Exception as ce:
                        _err(f"hCaptcha ошибка: {ce}")
                else:
                    # No providers — try clicking checkbox manually
                    await checkbox.click()
                    await _human_delay(3.0, 5.0)
                    _log("hCaptcha: клик по checkbox (нет провайдеров)")
        except Exception:
            _log("hCaptcha не обнаружена, пропуск")

        await _human_delay(2.0, 4.0)

        # ── Step 7: Skip recovery / Complete registration ──
        _log("Пропуск восстановления...")
        skip_selectors = [
            'button:has-text("Skip")',
            'button:has-text("Пропустить")',
            'button:has-text("Maybe later")',
            'button:has-text("Not now")',
        ]
        for sel in skip_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=5000):
                    await btn.click()
                    _log("Пропущено")
                    break
            except Exception:
                continue

        await _human_delay(3.0, 5.0)

        # ── Step 8: Verify success ──
        _log("Проверка результата...")
        await _debug_screenshot(page, "proton_result", _log)

        final_url = page.url
        registration_success = False

        # Check for success indicators
        success_indicators = [
            "mail",
            "inbox",
            "welcome",
            "congratulations",
            "setup",
        ]
        for indicator in success_indicators:
            if indicator in final_url.lower():
                registration_success = True
                break

        # Also check page content
        if not registration_success:
            try:
                page_text = await page.inner_text("body", timeout=5000)
                page_lower = page_text.lower()
                if any(x in page_lower for x in ["inbox", "welcome", "congratulations", "start using"]):
                    registration_success = True
            except Exception:
                pass

        # If still on signup page, try to detect if username was taken
        if not registration_success and "signup" in final_url.lower():
            try:
                error_text = await page.inner_text("body", timeout=3000)
                if "already used" in error_text.lower() or "not available" in error_text.lower():
                    _err(f"Username '{username}' уже занят")
                    return None
            except Exception:
                pass

        if not registration_success:
            _err(f"❌ Регистрация НЕ подтверждена! URL: {final_url}")
            await _debug_screenshot(page, "proton_not_confirmed", _log)
            return None

        # ── Save session and create account ──
        try:
            session_path = await browser_manager.save_session(context, 0)
        except Exception as se:
            logger.warning(f"[ProtonMail] Session save warning: {se}")
            session_path = None

        account = Account(
            email=email,
            password=password,
            provider="protonmail",
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

        logger.info(f"✅ ProtonMail registered: {email}")
        export_account_to_file(account)
        return account

    except Exception as e:
        logger.error(f"❌ ProtonMail registration failed: {e}", exc_info=True)
        _err(str(e)[:500])
        return None
    finally:
        ACTIVE_PAGES.pop(thread_id, None)
        try:
            await context.close()
        except Exception:
            pass
