"""
Leomail v3 — Tuta (Tutanota) Registration Engine
Registers tuta.com / tutanota.com / tutamail.com accounts.
Flow: tuta.com/#signup → plan → email+domain → password → clock-face CAPTCHA → recovery code
No phone verification required. Free accounts may require 48h activation wait.
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

# Available Tuta domains for free accounts
TUTA_DOMAINS = ["tutanota.com", "tuta.io", "tutamail.com", "tutanota.de", "keemail.me"]


async def register_single_tuta(
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
    """Register a single Tuta account with human-like behavior."""
    if ACTIVE_PAGES is None:
        ACTIVE_PAGES = {}
    if BIRTH_CANCEL_EVENT is None:
        BIRTH_CANCEL_EVENT = threading.Event()
    if not name_pool:
        logger.error("[Tuta] ❌ Нет имён! Загрузите пакет имён перед регистрацией.")
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
    domain = random.choice(TUTA_DOMAINS)
    email = f"{username}@{domain}"

    context = await browser_manager.create_context(
        proxy=proxy,
        device_type=device_type,
        geo=None,
    )

    def _log(msg: str):
        n = getattr(thread_log, '_worker_id', 0) + 1 if thread_log else '?'
        logger.info(f"[Tuta][Поток {n}] {msg}")
        if thread_log:
            thread_log.current_action = f"Поток {n}: {msg}"
            try:
                db.commit()
            except Exception:
                pass

    def _err(msg: str):
        n = getattr(thread_log, '_worker_id', 0) + 1 if thread_log else '?'
        logger.error(f"[Tuta][Поток {n}] {msg}")
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
        await page.goto("https://app.tuta.com/#signup", wait_until="domcontentloaded", timeout=60000)
        await _human_delay(3.0, 5.0)
        await _debug_screenshot(page, "tuta_signup_page", _log)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        # ── Step 2: Select Free plan ──
        _log("Выбор бесплатного плана...")
        free_plan_selectors = [
            'button:has-text("Free")',
            'button:has-text("Бесплатно")',
            'div:has-text("Free") >> button',
            '[data-signup-plan="Free"]',
        ]
        for sel in free_plan_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=5000):
                    await btn.click()
                    _log("Выбран бесплатный план")
                    break
            except Exception:
                continue
        await _human_delay(2.0, 3.0)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        # ── Step 3: Enter email address ──
        _log(f"Ввод email: {username}@{domain}")
        # Tuta has a username input + domain dropdown
        email_selectors = [
            'input[type="text"]',
            'input[name="mailAddress"]',
            'input[id="mailAddress"]',
            'input[aria-label*="address"]',
            'input[placeholder*="address"]',
        ]
        email_filled = False
        for sel in email_selectors:
            try:
                inp = page.locator(sel).first
                if await inp.is_visible(timeout=5000):
                    await _human_fill(page, sel, username)
                    email_filled = True
                    _log(f"Username введён: {username}")
                    break
            except Exception:
                continue

        if not email_filled:
            _err("Не найдено поле email")
            await _debug_screenshot(page, "tuta_no_email_field", _log)
            return None

        # Try to select domain from dropdown
        try:
            domain_dropdown = page.locator('select, [role="listbox"]').first
            if await domain_dropdown.is_visible(timeout=3000):
                await domain_dropdown.select_option(label=domain)
                _log(f"Домен выбран: {domain}")
        except Exception:
            _log(f"Домен по умолчанию (dropdown не найден)")

        await _human_delay(1.0, 2.0)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        # ── Step 4: Enter password ──
        _log("Ввод пароля...")
        password_selectors = [
            'input[type="password"]',
            'input[name="password"]',
            'input[autocomplete="new-password"]',
        ]
        password_fields = page.locator('input[type="password"]')
        pwd_count = await password_fields.count()

        if pwd_count >= 2:
            # First is password, second is confirm
            await password_fields.nth(0).fill("")
            await _human_type(page, 'input[type="password"]:nth-of-type(1)', password)
            await _human_delay(0.5, 1.0)
            await password_fields.nth(1).fill("")
            await password_fields.nth(1).type(password, delay=random.randint(30, 80))
            _log("Пароль введён и подтверждён")
        elif pwd_count == 1:
            await password_fields.nth(0).fill("")
            await password_fields.nth(0).type(password, delay=random.randint(30, 80))
            _log("Пароль введён (1 поле)")
        else:
            _err("Не найдены поля пароля")
            return None

        await _human_delay(1.0, 2.0)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        # ── Step 5: Accept terms ──
        _log("Принятие условий...")
        terms_selectors = [
            'input[type="checkbox"]',
            'label:has-text("terms")',
            'label:has-text("agree")',
            'label:has-text("условия")',
        ]
        for sel in terms_selectors:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=3000):
                    await el.click()
                    _log("Условия приняты")
                    break
            except Exception:
                continue

        # Second checkbox (age confirmation) if present
        try:
            checkboxes = page.locator('input[type="checkbox"]')
            count = await checkboxes.count()
            if count > 1:
                for i in range(count):
                    checked = await checkboxes.nth(i).is_checked()
                    if not checked:
                        await checkboxes.nth(i).click()
                        await _human_delay(0.3, 0.7)
        except Exception:
            pass

        await _human_delay(1.0, 2.0)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        # ── Step 6: Submit & Handle clock-face CAPTCHA ──
        _log("Отправка формы...")
        submit_selectors = [
            'button[type="submit"]',
            'button:has-text("Next")',
            'button:has-text("OK")',
            'button:has-text("Далее")',
            'button:has-text("Create account")',
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
        await _debug_screenshot(page, "tuta_after_submit", _log)

        # Handle Tuta clock-face CAPTCHA via CaptchaChain
        # Tuta uses a custom clock CAPTCHA: user must type time shown on clock (e.g. "08:30")
        _log("Проверка CAPTCHA (часы)...")
        try:
            # Look for clock captcha
            clock_captcha = page.locator('canvas, img[src*="captcha"], [class*="captcha"]').first
            if await clock_captcha.is_visible(timeout=10000):
                _log("Обнаружена clock CAPTCHA — решение через CaptchaChain...")
                captcha_input = page.locator('input[type="text"]').first
                if await captcha_input.is_visible(timeout=5000):
                    captcha_chain = get_captcha_chain()
                    solved = False
                    if captcha_chain.providers:
                        try:
                            captcha_screenshot = await clock_captcha.screenshot()
                            solution = await asyncio.wait_for(
                                asyncio.to_thread(
                                    captcha_chain.solve,
                                    "image",
                                    image_bytes=captcha_screenshot,
                                ),
                                timeout=60,
                            )
                            if solution:
                                await captcha_input.fill(solution)
                                _log(f"CAPTCHA решена через CaptchaChain: {solution}")
                                solved = True
                        except asyncio.TimeoutError:
                            _log("CAPTCHA solver таймаут, пробуем случайное время")
                        except Exception as ce:
                            _log(f"CAPTCHA solver ошибка: {ce}")

                    if not solved:
                        # Fallback: random plausible time
                        hour = random.randint(1, 12)
                        minute = random.choice([0, 15, 30, 45])
                        time_str = f"{hour:02d}:{minute:02d}"
                        await captcha_input.fill(time_str)
                        _log(f"CAPTCHA: случайное время {time_str}")

                    # Submit captcha
                    ok_btn = page.locator('button:has-text("OK"), button[type="submit"]').first
                    if await ok_btn.is_visible(timeout=3000):
                        await ok_btn.click()
                        _log("CAPTCHA отправлена")
            else:
                _log("CAPTCHA не обнаружена")
        except Exception as e:
            _log(f"CAPTCHA обработка: {e}")

        await _human_delay(5.0, 8.0)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        # ── Step 7: Save recovery code if shown ──
        _log("Проверка recovery code...")
        recovery_code = None
        try:
            # Tuta shows recovery code that must be saved
            code_element = page.locator('[class*="recovery"], pre, code, textarea[readonly]').first
            if await code_element.is_visible(timeout=5000):
                recovery_code = await code_element.inner_text()
                _log(f"Recovery code сохранён: {recovery_code[:20]}...")

                # Click OK/Next to proceed
                ok_selectors = ['button:has-text("OK")', 'button:has-text("Next")', 'button:has-text("Далее")']
                for sel in ok_selectors:
                    try:
                        btn = page.locator(sel).first
                        if await btn.is_visible(timeout=3000):
                            await btn.click()
                            break
                    except Exception:
                        continue
        except Exception:
            _log("Recovery code не показан")

        await _human_delay(3.0, 5.0)

        # ── Step 8: Verify success ──
        _log("Проверка результата...")
        await _debug_screenshot(page, "tuta_result", _log)

        final_url = page.url
        registration_success = False

        # Check URL for success indicators
        success_url_parts = ["mail", "inbox", "login", "setup"]
        for part in success_url_parts:
            if part in final_url.lower() and "signup" not in final_url.lower():
                registration_success = True
                break

        # Check page content
        pending_approval = False
        if not registration_success:
            try:
                page_text = await page.inner_text("body", timeout=5000)
                page_lower = page_text.lower()
                success_texts = ["inbox", "welcome", "congratulations", "registration successful",
                                "account created", "your address"]
                if any(x in page_lower for x in success_texts):
                    registration_success = True
                # 48h pending moderation detection
                pending_texts = ["approval", "pending", "48 hours", "review", "activation",
                                "will be activated", "wait", "verification pending"]
                if any(x in page_lower for x in pending_texts):
                    pending_approval = True
                    registration_success = True  # Account was created, just pending
                    _log("⚠️ Tuta: аккаунт создан, но ожидает модерации (48ч)")
            except Exception:
                pass

        if not registration_success:
            _err(f"❌ Регистрация НЕ подтверждена! URL: {final_url}")
            await _debug_screenshot(page, "tuta_not_confirmed", _log)
            return None

        # ── Save session and create account ──
        try:
            session_path = await browser_manager.save_session(context, 0)
        except Exception as se:
            logger.warning(f"[Tuta] Session save warning: {se}")
            session_path = None

        # Store recovery code in metadata
        metadata = {}
        if recovery_code:
            metadata["recovery_code"] = recovery_code

        account = Account(
            email=email,
            password=password,
            provider="tuta",
            first_name=first_name,
            last_name=last_name,
            gender="random",
            birthday=birthday,
            birth_ip=f"{proxy.host}" if proxy else None,
            status="pending_approval" if pending_approval else "new",
            metadata_blob=metadata,
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

        logger.info(f"✅ Tuta registered: {email}")
        export_account_to_file(account)
        return account

    except Exception as e:
        logger.error(f"❌ Tuta registration failed: {e}", exc_info=True)
        _err(str(e)[:500])
        return None
    finally:
        ACTIVE_PAGES.pop(thread_id, None)
        try:
            await context.close()
        except Exception:
            pass
