"""
Leomail v4 - Web.de Registration Engine
Registers @web.de accounts via registrierung.web.de.
Flow: navigate → name → email → password → birthday → phone/SMS OTP → CAPTCHA → done

IMPORTANT: Web.de blocks non-German IPs for registration.
           MUST use German proxy (geo=DE) or at minimum a European one.
           Site is in German — selectors use German labels.
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
    detect_and_solve_recaptcha as _detect_and_solve_recaptcha,
    debug_screenshot as _debug_screenshot,
    _safe_screenshot,
    scan_for_block_signals as _scan_for_block_signals,
    clean_session as _clean_session,
    rate_limiter as _rate_limiter,
    RateLimitError, BannedIPError, FatalError, RecoverableError, CaptchaFailError,
    RegContext, verify_page_state, block_check, run_step,
    get_expected_language,
    run_flow_machine,
    get_sms_chain, PHONE_COUNTRY_MAP,
    export_account_to_file,
)

# Registration URL
SIGNUP_URL = "https://registrierung.web.de/"

# Webmail inbox
MAIL_URL = "https://web.de/email/"


# ── Step Functions ───────────────────────────────────────────────────────────────


async def step_0_warmup(page, ctx: RegContext):
    """Step 0: Pre-registration warmup — natural browsing history."""
    ctx._log("Pre-registration warmup (browsing)...")
    try:
        geo = getattr(ctx, 'proxy_geo', None)
        await pre_registration_warmup(page, geo=geo)
    except Exception as warmup_e:
        logger.debug(f"[Web.de] Warmup error: {warmup_e}")


async def step_1_navigate(page, ctx: RegContext, proxy, db):
    """Step 1: Navigate to registrierung.web.de.
    Web.de requires German IP — check for geo-block page.
    """
    ctx._log("Navigating to Web.de registration...")

    # Cookie warmup — visit web.de first
    try:
        await page.goto("https://web.de", wait_until="domcontentloaded", timeout=20000)
        await random_scroll(page, "down")
        await _human_delay(2, 4)
    except Exception as e:
        logger.debug(f"[Web.de] Cookie warmup failed: {e}")

    # Navigate to registration page
    await page.goto(SIGNUP_URL, wait_until="domcontentloaded", timeout=30000)
    await _human_delay(2, 4)

    # Check for geo-block — "Registrierung leider nicht möglich"
    page_text = await page.inner_text("body")
    if "nicht möglich" in page_text or "nicht zugelassenen IP" in page_text:
        ctx._err("[E501] Registration blocked — non-German IP detected. Need DE proxy.")
        raise RecoverableError("[E501] Web.de requires German IP for registration")

    # Check we're on the registration form
    form_selectors = [
        'input[name="firstName"]', 'input[name="vorname"]',
        'input[id="firstName"]', 'input[id="vorname"]',
        'input[placeholder*="Vorname"]', 'input[placeholder*="First"]',
        '#firstName', '#vorname',
        'input[autocomplete="given-name"]',
    ]
    found = await _wait_for_any(page, form_selectors, timeout=10000)
    if not found:
        # Maybe it's a multi-step form — look for any visible input
        any_input = await _wait_for_any(page, ['input[type="text"]', 'input[type="email"]'], timeout=5000)
        if not any_input:
            ctx._err("[E101] Registration form not found")
            raise RecoverableError("[E101] Web.de registration form not loaded")

    ctx._log("Registration page loaded")


async def step_2_fill_name(page, ctx: RegContext):
    """Step 2: Fill first name and last name."""
    ctx._log(f"Filling name: {ctx.first_name} {ctx.last_name}")

    # First name — defensive multi-selector
    first_name_selectors = [
        'input[name="firstName"]', 'input[name="vorname"]',
        'input[id="firstName"]', 'input[id="vorname"]',
        'input[placeholder*="Vorname"]', 'input[placeholder*="First"]',
        'input[autocomplete="given-name"]',
        'input[aria-label*="Vorname"]', 'input[aria-label*="First"]',
    ]
    fn_field = await _wait_for_any(page, first_name_selectors, timeout=8000)
    if not fn_field:
        ctx._err("[E102] First name field not found")
        raise RecoverableError("[E102] First name field not found")
    await _human_fill(page, fn_field, ctx.first_name)
    await _human_delay(0.5, 1.5)

    # Last name
    last_name_selectors = [
        'input[name="lastName"]', 'input[name="nachname"]',
        'input[id="lastName"]', 'input[id="nachname"]',
        'input[placeholder*="Nachname"]', 'input[placeholder*="Last"]',
        'input[autocomplete="family-name"]',
        'input[aria-label*="Nachname"]', 'input[aria-label*="Last"]',
    ]
    ln_field = await _wait_for_any(page, last_name_selectors, timeout=5000)
    if not ln_field:
        ctx._err("[E102] Last name field not found")
        raise RecoverableError("[E102] Last name field not found")
    await _human_fill(page, ln_field, ctx.last_name)
    await _human_delay(0.5, 1.5)


async def step_3_fill_email(page, ctx: RegContext):
    """Step 3: Enter desired email address (Wunsch-E-Mail-Adresse)."""
    ctx._log(f"Entering desired email: {ctx.username}")

    email_selectors = [
        'input[name="email"]', 'input[name="wunschname"]',
        'input[name="wunschadresse"]', 'input[name="username"]',
        'input[id="email"]', 'input[id="wunschname"]',
        'input[id="wunschadresse"]', 'input[id="username"]',
        'input[placeholder*="Wunsch"]', 'input[placeholder*="E-Mail"]',
        'input[placeholder*="email"]', 'input[placeholder*="address"]',
        'input[autocomplete="email"]', 'input[autocomplete="username"]',
        'input[aria-label*="E-Mail"]', 'input[aria-label*="Wunsch"]',
    ]
    email_field = await _wait_for_any(page, email_selectors, timeout=8000)
    if not email_field:
        ctx._err("[E102] Email/username field not found")
        raise RecoverableError("[E102] Email field not found")

    # Only enter the username part (before @web.de)
    username = ctx.username
    if "@" in username:
        username = username.split("@")[0]
    await _human_fill(page, email_field, username)
    await _human_delay(1, 2)

    # Check if email is available — look for error/taken message
    try:
        error_el = page.locator('[class*="error"], [class*="Error"], [class*="alert"]')
        if await error_el.first.is_visible(timeout=2000):
            err_text = await error_el.first.inner_text()
            if "vergeben" in err_text.lower() or "taken" in err_text.lower() or "nicht verfügbar" in err_text.lower():
                ctx._log(f"Email taken, trying alternative: {username}1")
                await _human_fill(page, email_field, f"{username}{random.randint(10, 99)}")
                await _human_delay(1, 2)
    except Exception:
        pass


async def step_4_fill_password(page, ctx: RegContext):
    """Step 4: Create password.
    Web.de requires strong password (8+ chars, mixed case, numbers, special).
    """
    ctx._log("Setting password...")

    pwd_selectors = [
        'input[name="password"]', 'input[name="passwort"]',
        'input[id="password"]', 'input[id="passwort"]',
        'input[type="password"]',
        'input[placeholder*="Passwort"]', 'input[placeholder*="Password"]',
        'input[autocomplete="new-password"]',
        'input[aria-label*="Passwort"]', 'input[aria-label*="Password"]',
    ]
    pwd_field = await _wait_for_any(page, pwd_selectors, timeout=8000)
    if not pwd_field:
        ctx._err("[E103] Password field not found")
        raise RecoverableError("[E103] Password field not found")
    await _human_fill(page, pwd_field, ctx.password, field_type="password")
    await _human_delay(0.5, 1.5)

    # Confirm password (if present)
    confirm_selectors = [
        'input[name="passwordConfirm"]', 'input[name="passwortConfirm"]',
        'input[name="password_confirm"]', 'input[name="confirmPassword"]',
        'input[id="passwordConfirm"]', 'input[id="passwortConfirm"]',
        'input[placeholder*="bestätigen"]', 'input[placeholder*="Confirm"]',
        'input[placeholder*="wiederholen"]',
    ]
    confirm_field = await _wait_for_any(page, confirm_selectors, timeout=3000)
    if confirm_field:
        await _human_fill(page, confirm_field, ctx.password, field_type="password")
        await _human_delay(0.5, 1.0)


async def step_5_birthday(page, ctx: RegContext, birthday):
    """Step 5: Enter date of birth (Geburtsdatum).
    Birthday is (year, month, day) tuple.
    Web.de uses German date format: DD.MM.YYYY or separate select fields.
    """
    year, month, day = birthday
    ctx._log(f"Entering birthday: {day:02d}.{month:02d}.{year}")

    # Try a single combined date input first (DD.MM.YYYY)
    date_selectors = [
        'input[name="birthday"]', 'input[name="geburtsdatum"]',
        'input[name="birthDate"]', 'input[id="birthday"]',
        'input[id="geburtsdatum"]', 'input[type="date"]',
        'input[placeholder*="TT.MM.JJJJ"]', 'input[placeholder*="Geburts"]',
    ]
    date_field = await _wait_for_any(page, date_selectors, timeout=5000)
    if date_field:
        date_str = f"{day:02d}.{month:02d}.{year}"
        await _human_fill(page, date_field, date_str)
        await _human_delay(0.5, 1.0)
        return

    # Try separate day/month/year fields
    day_selectors = [
        'input[name="birthDay"]', 'input[name="day"]', 'input[name="tag"]',
        'select[name="birthDay"]', 'select[name="day"]', 'select[name="tag"]',
        'input[placeholder*="Tag"]', 'input[placeholder*="TT"]',
        'input[id="birthDay"]', 'input[id="day"]',
    ]
    month_selectors = [
        'input[name="birthMonth"]', 'input[name="month"]', 'input[name="monat"]',
        'select[name="birthMonth"]', 'select[name="month"]', 'select[name="monat"]',
        'input[placeholder*="Monat"]', 'input[placeholder*="MM"]',
        'input[id="birthMonth"]', 'input[id="month"]',
    ]
    year_selectors = [
        'input[name="birthYear"]', 'input[name="year"]', 'input[name="jahr"]',
        'select[name="birthYear"]', 'select[name="year"]', 'select[name="jahr"]',
        'input[placeholder*="Jahr"]', 'input[placeholder*="JJJJ"]',
        'input[id="birthYear"]', 'input[id="year"]',
    ]

    day_field = await _wait_for_any(page, day_selectors, timeout=5000)
    if day_field:
        if "select" in day_field:
            await page.select_option(day_field, str(day))
        else:
            await _human_fill(page, day_field, str(day))
        await _human_delay(0.3, 0.7)

    month_field = await _wait_for_any(page, month_selectors, timeout=3000)
    if month_field:
        if "select" in month_field:
            await page.select_option(month_field, str(month))
        else:
            await _human_fill(page, month_field, str(month))
        await _human_delay(0.3, 0.7)

    year_field = await _wait_for_any(page, year_selectors, timeout=3000)
    if year_field:
        if "select" in year_field:
            await page.select_option(year_field, str(year))
        else:
            await _human_fill(page, year_field, str(year))
        await _human_delay(0.3, 0.7)

    # If no fields found at all, log but don't crash (might be on a different step)
    if not day_field and not date_field:
        ctx._log("[WARN] Birthday fields not found — might be on wrong step or optional")


async def step_6_phone_sms(page, ctx: RegContext, sms_provider, proxy, db, thread_log, cancel_event=None):
    """Step 6: Enter phone number and verify SMS OTP.
    Web.de requires phone for registration — not optional.
    Uses SMS chain (5SIM → GrizzlySMS → SimSMS) with auto-fallback.
    """
    ctx._log("Phone number + SMS verification...")

    # Find phone input
    phone_selectors = [
        'input[name="phone"]', 'input[name="mobilfunknummer"]',
        'input[name="mobile"]', 'input[name="phoneNumber"]',
        'input[id="phone"]', 'input[id="mobilfunknummer"]',
        'input[type="tel"]',
        'input[placeholder*="Mobilfunknummer"]', 'input[placeholder*="Phone"]',
        'input[placeholder*="Handy"]', 'input[placeholder*="Telefon"]',
        'input[autocomplete="tel"]',
        'input[aria-label*="Mobilfunknummer"]', 'input[aria-label*="Phone"]',
    ]
    phone_field = await _wait_for_any(page, phone_selectors, timeout=10000)
    if not phone_field:
        ctx._log("[WARN] Phone field not found — might not be required or on different step")
        return

    # Get SMS chain
    chain = get_sms_chain()
    if not chain:
        ctx._err("[E401] No SMS providers configured")
        raise FatalError("[E401] No SMS providers — add 5SIM/GrizzlySMS/SimSMS in Settings")

    # For Web.de, prefer German numbers (DE) for higher acceptance
    sms_countries = ["de", "at", "nl", "pl", "cz", "fr", "es", "it"]

    order = None
    active_provider = None
    phone_number = ""
    order_id = ""

    # Try each provider in chain
    for chain_name, prov in chain:
        try:
            # Try "webde" service first, fall back to "other"
            for service_name in ["webde", "other", "gmail"]:
                try:
                    result = prov.order_number_from_countries(
                        service=service_name,
                        countries=sms_countries,
                    )
                    if result and result.get("number"):
                        order = result
                        active_provider = prov
                        phone_number = result["number"]
                        order_id = str(result.get("id", ""))
                        ctx._log(f"SMS: {chain_name} | service={service_name} | {phone_number}")
                        break
                except Exception as e:
                    logger.debug(f"[Web.de] SMS {chain_name}/{service_name} failed: {e}")
            if order:
                break
        except Exception as e:
            logger.debug(f"[Web.de] SMS chain {chain_name} failed: {e}")
            continue

    if not order:
        ctx._err("[E401] No SMS numbers available for web.de from any provider")
        raise RecoverableError("[E401] SMS number order failed")

    # Track active SMS for crash cleanup (/Economist — don't waste money)
    ctx._active_sms = {"provider": active_provider, "order_id": order_id, "number": phone_number}

    # Format phone number with + prefix
    display_number = phone_number
    if not display_number.startswith("+"):
        display_number = f"+{display_number}"
    ctx._display_phone = display_number  # Store for export

    # Enter phone number
    await _human_fill(page, phone_field, display_number)
    await _human_delay(1, 2)

    # Click submit/send code
    send_code_selectors = [
        'button:has-text("Code senden")',
        'button:has-text("SMS senden")',
        'button:has-text("Bestätigungscode")',
        'button:has-text("Send")',
        'button[type="submit"]',
        'input[type="submit"]',
        '#sendCode', '#submitPhone',
    ]
    send_btn = await _wait_for_any(page, send_code_selectors, timeout=5000)
    if send_btn:
        await _human_click(page, send_btn)
    else:
        await page.keyboard.press("Enter")
    await _human_delay(3, 6)

    # Wait for OTP code input to appear
    otp_selectors = [
        'input[name="code"]', 'input[name="otp"]',
        'input[name="verificationCode"]', 'input[name="smsCode"]',
        'input[id="code"]', 'input[id="otp"]',
        'input[placeholder*="Code"]', 'input[placeholder*="SMS"]',
        'input[aria-label*="Code"]', 'input[aria-label*="Bestätigungs"]',
        'input[maxlength="6"]', 'input[maxlength="4"]',
    ]
    otp_field = await _wait_for_any(page, otp_selectors, timeout=15000)
    if not otp_field:
        ctx._err("[E402] OTP code input not found after sending SMS")
        try:
            if hasattr(active_provider, 'cancel_number'):
                await asyncio.to_thread(active_provider.cancel_number, order_id)
        except Exception:
            pass
        raise RecoverableError("[E402] OTP field did not appear")

    # Wait for SMS code (blocking call with timeout, like Yahoo)
    ctx._log("Waiting for SMS code...")
    sms_result = await asyncio.to_thread(
        active_provider.get_sms_code, order_id, 300, cancel_event
    )
    sms_code = None
    if isinstance(sms_result, dict):
        sms_code = sms_result.get("code")
        if sms_result.get("error"):
            ctx._err(f"SMS error: {sms_result['error']}")
            try:
                if hasattr(active_provider, 'cancel_number'):
                    await asyncio.to_thread(active_provider.cancel_number, order_id)
            except Exception:
                pass
            raise RecoverableError("[E403] SMS error")
    elif isinstance(sms_result, str):
        sms_code = sms_result

    if not sms_code:
        ctx._err("[E403] SMS code not received within timeout")
        try:
            if hasattr(active_provider, 'cancel_number'):
                await asyncio.to_thread(active_provider.cancel_number, order_id)
        except Exception:
            pass
        raise RecoverableError("[E403] SMS code timeout")

    # Enter OTP code
    await _human_fill(page, otp_field, sms_code)
    await _human_delay(0.5, 1.5)

    # Submit OTP
    verify_selectors = [
        'button:has-text("Bestätigen")',
        'button:has-text("Verify")',
        'button:has-text("Prüfen")',
        'button[type="submit"]',
        'input[type="submit"]',
    ]
    verify_btn = await _wait_for_any(page, verify_selectors, timeout=5000)
    if verify_btn:
        await _human_click(page, verify_btn)
    else:
        await page.keyboard.press("Enter")
    await _human_delay(3, 6)

    # Mark SMS order as completed
    try:
        if hasattr(active_provider, 'complete_activation'):
            await asyncio.to_thread(active_provider.complete_activation, order_id)
    except Exception:
        pass


async def step_7_captcha(page, ctx: RegContext, captcha_provider):
    """Step 7: Handle CAPTCHA if present.
    Web.de uses either invisible reCAPTCHA or CaptchaFox (drag-and-drop).
    """
    ctx._log("Checking for CAPTCHA...")

    # Check for reCAPTCHA
    recaptcha_selectors = [
        'iframe[src*="recaptcha"]',
        'iframe[title*="reCAPTCHA"]',
        '.g-recaptcha',
        '#g-recaptcha',
        'div[data-sitekey]',
    ]
    recaptcha = await _wait_for_any(page, recaptcha_selectors, timeout=5000)
    if recaptcha:
        ctx._log("reCAPTCHA detected — solving...")
        try:
            solved = await _detect_and_solve_recaptcha(page, captcha_provider, ctx)
            if not solved:
                ctx._err("[E410] reCAPTCHA solve failed")
                raise CaptchaFailError("[E410] reCAPTCHA not solved")
            ctx._log("reCAPTCHA solved!")
        except CaptchaFailError:
            raise
        except Exception as e:
            ctx._err(f"[E411] reCAPTCHA error: {e}")
            raise CaptchaFailError(f"[E411] reCAPTCHA error: {e}")
        return

    # Check for CaptchaFox or other drag-and-drop
    captchafox_selectors = [
        'iframe[src*="captchafox"]',
        '#captchafox',
        'div[data-captchafox]',
    ]
    captchafox = await _wait_for_any(page, captchafox_selectors, timeout=3000)
    if captchafox:
        ctx._log("[WARN] CaptchaFox detected — not yet supported, trying to proceed...")
        # CaptchaFox is a newer CAPTCHA — may need specific solver
        # For now, try to click "I am human" if it's that simple
        try:
            human_btn = page.locator('button:has-text("Ich bin ein Mensch"), button:has-text("I am human")')
            if await human_btn.first.is_visible(timeout=2000):
                await human_btn.first.click()
                await _human_delay(2, 4)
                return
        except Exception:
            pass
        ctx._log("CaptchaFox — attempting to submit anyway (might be invisible)")
        return

    # No CAPTCHA found — might be invisible or already solved
    ctx._log("No visible CAPTCHA detected — proceeding")


async def step_8_submit(page, ctx: RegContext):
    """Step 8: Accept terms and submit registration form."""
    ctx._log("Submitting registration...")

    # Check/accept terms checkbox (if present)
    terms_selectors = [
        'input[name="agb"]', 'input[name="terms"]',
        'input[name="acceptTerms"]', 'input[type="checkbox"]',
        '#agb', '#terms', '#acceptTerms',
        'label:has-text("AGB")', 'label:has-text("Terms")',
        'label:has-text("Ich akzeptiere")',
    ]
    terms = await _wait_for_any(page, terms_selectors, timeout=3000)
    if terms:
        try:
            checkbox = page.locator(terms).first
            if not await checkbox.is_checked():
                await checkbox.click()
                await _human_delay(0.5, 1.0)
        except Exception:
            pass

    # Click register/submit button
    submit_selectors = [
        'button:has-text("Registrieren")',
        'button:has-text("Konto erstellen")',
        'button:has-text("Account erstellen")',
        'button:has-text("Create")',
        'button:has-text("Weiter")',
        'input[value="Registrieren"]',
        'button[type="submit"]',
        'input[type="submit"]',
    ]
    submit_btn = await _wait_for_any(page, submit_selectors, timeout=8000)
    if submit_btn:
        await _human_click(page, submit_btn)
    else:
        await page.keyboard.press("Enter")
    await _human_delay(5, 10)

    # Check for errors after submission
    try:
        error_el = page.locator('[class*="error"], [class*="Error"], [role="alert"]')
        if await error_el.first.is_visible(timeout=3000):
            err_text = await error_el.first.inner_text()
            if err_text.strip():
                ctx._err(f"[E104] Registration error: {err_text[:200]}")
                raise RecoverableError(f"[E104] {err_text[:200]}")
    except RecoverableError:
        raise
    except Exception:
        pass


async def step_9_verify_success(page, ctx: RegContext) -> bool:
    """Step 9: Verify registration was successful.
    After registration, Web.de redirects to inbox or shows welcome page.
    """
    ctx._log("Verifying registration success...")

    # Check URL for success indicators
    current_url = page.url or ""
    success_indicators = [
        "mail", "postfach", "inbox", "willkommen", "welcome",
        "web.de/email", "navigator.web.de",
    ]
    for indicator in success_indicators:
        if indicator in current_url.lower():
            ctx._log(f"SUCCESS: landed on {current_url[:80]}")
            return True

    # Check for welcome/inbox elements
    inbox_selectors = [
        'button:has-text("Neue E-Mail")',
        'button:has-text("New Email")',
        'a:has-text("Posteingang")',
        'a:has-text("Inbox")',
        '[aria-label="Posteingang"]',
        '[aria-label="Inbox"]',
    ]
    inbox_found = await _wait_for_any(page, inbox_selectors, timeout=15000)
    if inbox_found:
        ctx._log("SUCCESS: inbox elements detected")
        return True

    # Check for "Glückwunsch" (congratulations) or welcome message
    try:
        body_text = await page.inner_text("body")
        if any(x in body_text.lower() for x in ["glückwunsch", "erfolgreich", "willkommen", "congratulations"]):
            ctx._log("SUCCESS: welcome/success message detected")
            return True
    except Exception:
        pass

    # Wait a bit more and check URL again
    await _human_delay(5, 8)
    current_url = page.url or ""
    if "registrierung" not in current_url.lower():
        ctx._log(f"Likely success: left registration page → {current_url[:80]}")
        return True

    ctx._err("[E502] Registration success not confirmed")
    return False


# ── Main entry point ──────────────────────────────────────────────────────────


ACTIVE_PAGES: dict = {}


async def register_single_webde(
    browser_manager: BrowserManager,
    proxy: Proxy,
    name_pool: list,
    captcha_provider,
    db: Session,
    thread_log: ThreadLog,
    sms_provider=None,
    ACTIVE_PAGES: dict = None,
    BIRTH_CANCEL_EVENT: threading.Event = None,
) -> Account | None:
    """
    Register a single Web.de account.

    Returns Account on success, None on failure.
    """
    if ACTIVE_PAGES is None:
        ACTIVE_PAGES = {}

    cancel_event = BIRTH_CANCEL_EVENT or threading.Event()

    # Validate name pool
    if not name_pool:
        if thread_log:
            thread_log.status = "error"
            thread_log.error_message = "No names! Load a name pack."
            try: db.commit()
            except: pass
        return None

    first_name, last_name = random.choice(name_pool)
    password = generate_password()
    birthday = generate_birthday()
    username = generate_username(first_name, last_name)
    email = f"{username}@web.de"

    # ── Create RegContext ──
    def _log(msg: str):
        n = getattr(thread_log, '_worker_id', 0) + 1 if thread_log else '?'
        logger.info(f"[Web.de][Thread {n}] {msg}")
        if thread_log:
            thread_log.current_action = f"Thread {n}: {msg}"
            try: db.commit()
            except Exception: pass

    def _err(msg: str):
        n = getattr(thread_log, '_worker_id', 0) + 1 if thread_log else '?'
        logger.error(f"[Web.de][Thread {n}] {msg}")
        if thread_log:
            thread_log.error_message = f"Thread {n}: {msg}"[:500]
            try: db.commit()
            except Exception: pass

    _proxy_geo = (proxy.geo or "").upper() if proxy else ""
    ctx = RegContext(
        provider="webde",
        username=username,
        password=password,
        email=email,
        first_name=first_name,
        last_name=last_name,
        proxy_ip=f"{proxy.host}:{proxy.port}" if proxy else "",
        proxy_geo=_proxy_geo,
        proxy_type=getattr(proxy, 'proxy_type', '') or "" if proxy else "",
        language=get_expected_language(_proxy_geo),
        thread_id=thread_log.id if thread_log else 0,
        _log=_log,
        _err=_err,
    )

    ctx._active_sms = None
    _sms_success = False

    context = await browser_manager.create_context(proxy=proxy, geo=None)

    try:
        page = await context.new_page()
        ACTIVE_PAGES[ctx.thread_id] = {"page": page, "context": context}

        # ── Run registration flow ──
        steps = [
            ("warmup", step_0_warmup, (ctx,)),
            ("navigate", step_1_navigate, (ctx, proxy, db)),
            ("fill_name", step_2_fill_name, (ctx,)),
            ("fill_email", step_3_fill_email, (ctx,)),
            ("fill_password", step_4_fill_password, (ctx,)),
            ("birthday", step_5_birthday, (ctx, birthday)),
        ]
        await run_flow_machine(page, ctx, steps, cancel_event)

        # Phone SMS verification (requires sms_provider from chain)
        await step_6_phone_sms(page, ctx, sms_provider, proxy, db, thread_log, cancel_event)

        # CAPTCHA
        await step_7_captcha(page, ctx, captcha_provider)

        # Submit form
        await step_8_submit(page, ctx)

        # Verify success
        success = await step_9_verify_success(page, ctx)

        if success:
            # Get final email from page (might have been modified by availability check)
            try:
                # Try to read actual email from page/URL
                actual_email = email  # fallback
                page_text = await page.inner_text("body")
                if "@web.de" in page_text:
                    import re
                    found_emails = re.findall(r'[\w.+-]+@web\.de', page_text)
                    if found_emails:
                        actual_email = found_emails[0]
            except Exception:
                actual_email = email

            # Create account record
            account = Account(
                email=actual_email,
                password=password,
                provider="webde",
                first_name=first_name,
                last_name=last_name,
                birthday=f"{birthday[0]}-{birthday[1]:02d}-{birthday[2]:02d}",
                status="New",
                user_agent=await page.evaluate("() => navigator.userAgent"),
                birth_ip=ctx.proxy_ip,
                geo=_proxy_geo,
            )
            db.add(account)
            db.commit()
            db.refresh(account)

            # Save session + fingerprint (matching Yahoo pattern)
            try:
                account.browser_profile_path = await browser_manager.save_session(context, account.id)
                db.commit()
                _log("Browser session saved")
            except Exception as se:
                _log(f"Session save warning: {se}")

            try:
                fp_data = getattr(context, '_leomail_fingerprint', None)
                if fp_data:
                    browser_manager.save_fingerprint(account.id, fp_data)
                    account.user_agent = fp_data.get("user_agent", "")
                    db.commit()
                    _log("Fingerprint saved")
            except Exception as fe:
                _log(f"Fingerprint save warning: {fe}")

            # Export to file
            _sms_success = True
            display_phone = getattr(ctx, '_display_phone', '')
            export_account_to_file(account, {"sms_phone": display_phone})

            _log(f"✓ Registered: {actual_email}")
            return account
        else:
            _err("Registration verification failed")
            return None

    except (FatalError, BannedIPError) as e:
        _err(f"Fatal: {e}")
        if thread_log:
            thread_log.error_message = str(e)[:500]
            try: db.commit()
            except: pass
        return None
    except RecoverableError as e:
        _err(f"Recoverable: {e}")
        if thread_log:
            thread_log.error_message = str(e)[:500]
            try: db.commit()
            except: pass
        return None
    except Exception as e:
        _err(f"Unexpected: {e}")
        if thread_log:
            thread_log.error_message = f"Unexpected: {str(e)[:400]}"
            try: db.commit()
            except: pass
        return None
    finally:
        # Cancel SMS number if we ordered one but didn't complete registration
        if ctx._active_sms and not _sms_success:
            try:
                await asyncio.to_thread(
                    ctx._active_sms["provider"].cancel_number,
                    ctx._active_sms["order_id"]
                )
                _log(f"SMS cancelled (crash recovery): {ctx._active_sms['number']}")
            except Exception:
                pass
        ACTIVE_PAGES.pop(ctx.thread_id, None)
        try:
            await context.close()
        except Exception:
            pass
