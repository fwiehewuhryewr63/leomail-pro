"""
Leomail v4 - Gmail Registration Engine (Defensive Coding Template)
Registers gmail.com accounts via Google signup.
Flow: signup -> name -> birthday+gender -> username -> password -> (SMS) -> (recovery) -> TOS -> done
Requires SMS for phone verification (SimSMS/Grizzly/5SIM chain).
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
    scan_for_block_signals as _scan_for_block_signals,
    clean_session as _clean_session,
    rate_limiter as _rate_limiter,
    RateLimitError, BannedIPError, FatalError, RecoverableError, CaptchaFailError,
    RegContext, verify_page_state, block_check, run_step,
    PHONE_COUNTRY_MAP, COUNTRY_TO_ISO2, PREFIX_TO_SMS_COUNTRY,
    order_sms_with_chain, get_next_sms_number,
    reset_chain_state, SMS_CODE_TIMEOUT,
    export_account_to_file,
)


# ── Step Functions ───────────────────────────────────────────────────────────────


async def step_0_warmup(page, ctx: RegContext):
    """Step 0: Session warmup — visit Google/YouTube to build trust score."""
    ctx._log("Session warmup (realistic)...")
    warmup_sites = [
        ("https://www.google.com", 2, 4),
        ("https://www.youtube.com", 2, 3),
        ("https://news.google.com", 1, 2),
    ]
    for site_url, min_t, max_t in random.sample(warmup_sites, random.randint(2, 3)):
        try:
            await page.goto(site_url, wait_until="domcontentloaded", timeout=15000)
            await _human_delay(min_t, max_t)
            await random_mouse_move(page, steps=random.randint(2, 4))
            await random_scroll(page)
        except Exception:
            pass
    ctx._log("Warmup completed")


async def step_1_navigate(page, ctx: RegContext, proxy, db):
    """Step 1: Navigate to Google signup. Checks: dead proxy, block signals."""
    ctx._log("Opening Google registration page...")
    try:
        await page.goto(
            "https://accounts.google.com/signup/v2/webcreateaccount?flowName=GlifWebSignIn&flowEntry=SignUp",
            wait_until="domcontentloaded",
            timeout=60000,
        )
    except Exception as nav_e:
        logger.warning(f"[Gmail] Navigation error: {nav_e}")

    await _human_delay(2, 4)

    # Pre-check: proxy alive?
    current_url = page.url or ""
    if "chrome-error" in current_url or "about:blank" == current_url:
        ctx._err(f"[ERR] Proxy DEAD - page failed to load (URL: {current_url})")
        if proxy:
            try:
                proxy.status = ProxyStatus.DEAD
                proxy.fail_count = (proxy.fail_count or 0) + 1
                db.commit()
            except Exception:
                pass
        raise FatalError("E501", f"Proxy dead: {current_url}")

    # Block scan
    await block_check(page, ctx.provider, ctx, "navigate")

    await random_mouse_move(page, steps=3)
    ctx._log(f"Page: {page.url}")


async def step_2_name(page, ctx: RegContext, captcha_provider):
    """Step 2: Enter first name + last name and click Next."""
    await block_check(page, ctx.provider, ctx, "name")

    ctx._log(f"Entering name: {ctx.first_name} {ctx.last_name}")
    fn_sel = await _wait_and_find(page, [
        'input[name="firstName"]', '#firstName',
        'input[aria-label*="irst"]', 'input[aria-label*="имя"]',
        'input[placeholder*="First"]', 'input[placeholder*="имя"]',
        'input[autocomplete="given-name"]',
    ], "gmail_firstname", ctx.username, ctx._log, ctx._err, timeout=20000)
    if not fn_sel:
        raise RecoverableError("E101", "First name field not found")

    await _human_fill(page, fn_sel, ctx.first_name)

    ln_sel = await _wait_for_any(page, [
        'input[name="lastName"]', '#lastName',
        'input[aria-label*="ast"]', 'input[aria-label*="фам"]',
        'input[placeholder*="Last"]', 'input[placeholder*="фам"]',
        'input[autocomplete="family-name"]',
    ], timeout=5000)
    if ln_sel:
        await _human_delay(0.3, 0.6)
        await _human_fill(page, ln_sel, ctx.last_name)

    await _human_delay(0.5, 1)

    # Click Next
    next_btn = await _wait_for_any(page, [
        'button:has-text("Next")', '#accountDetailsNext button',
        'button[type="button"]', '#accountDetailsNext',
        'div[id*="Next"] button', 'span:has-text("Next")',
    ], timeout=5000)
    if next_btn:
        await page.locator(next_btn).first.click()
    else:
        await page.keyboard.press("Enter")
    await _human_delay(3, 5)

    # Check CAPTCHA after name step
    await _detect_and_solve_recaptcha(page, captcha_provider, ctx._log)
    await between_steps(page)


async def step_3_birthday_gender(page, ctx: RegContext):
    """Step 3: Enter birthday + gender and click Next."""
    ctx._log("Entering date of birth...")
    birthday = generate_birthday()
    # Store birthday for later use
    ctx._birthday = birthday

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
            await _human_fill(page, day_sel, str(birthday.day), field_type="password")

        year_sel = await _wait_for_any(page, ['input#year', '#year', 'input[name="year"]'], timeout=5000)
        if year_sel:
            await _human_fill(page, year_sel, str(birthday.year), field_type="password")

        await _human_delay(0.3, 0.6)

        gender_sel = await _wait_for_any(page, ['select#gender', '#gender', 'select[name="gender"]'], timeout=5000)
        if gender_sel:
            gender_val = random.choice(["1", "2"])  # 1=Male, 2=Female
            await page.locator(gender_sel).first.select_option(gender_val)
            ctx._gender = "male" if gender_val == "1" else "female"
        else:
            ctx._gender = "random"

        await _human_delay(0.5, 1)
        next_btn = await _wait_for_any(page, [
            'button:has-text("Next")', '#birthdaygenderNext button'
        ], timeout=5000)
        if next_btn:
            await page.locator(next_btn).first.click()
        else:
            await page.keyboard.press("Enter")
        await _human_delay(3, 5)
    else:
        ctx._log("[SKIP] Birthday page not shown")
        ctx._gender = "random"


async def step_4_username(page, ctx: RegContext):
    """Step 4: Choose username. Handles: 'Create your own' option, username taken retry."""
    await block_check(page, ctx.provider, ctx, "username")

    ctx._log(f"Entering username: {ctx.username}")

    # Google may show "Create your own" or suggested usernames
    create_own = page.locator(
        'div[data-value="custom"], label:has-text("Create your own"), '
        'label:has-text("Создайте собственный")'
    )
    try:
        if await create_own.count() > 0:
            await create_own.first.click()
            await _human_delay(1, 2)
    except Exception:
        pass

    username_sel = await _wait_for_any(page, [
        'input[name="Username"]', '#username', 'input[type="text"][aria-label*="user"]'
    ], timeout=10000)
    if username_sel:
        await page.locator(username_sel).first.click()
        await _human_delay(0.3, 0.6)
        await page.locator(username_sel).first.fill("")
        for char in ctx.username:
            await page.locator(username_sel).first.type(char, delay=random.randint(50, 100))
    else:
        ctx._log("Username field not found, Google may have offered auto-selection")

    await _human_delay(0.5, 1)
    next_btn = await _wait_for_any(page, ['button:has-text("Next")'], timeout=5000)
    if next_btn:
        await page.locator(next_btn).first.click()
    else:
        await page.keyboard.press("Enter")
    await _human_delay(3, 5)

    # Check for username taken error
    err_el = page.locator(
        'div[class*="error"], div[jsname*="error"], '
        'div:has-text("already taken"), div:has-text("already takenо")'
    )
    err_text = None
    try:
        if await err_el.count() > 0:
            err_text = await err_el.first.text_content()
    except Exception:
        pass

    if err_text and ("taken" in err_text.lower() or "занято" in err_text.lower()):
        ctx._log("Username taken, trying another...")
        ctx.username = generate_username(ctx.first_name, ctx.last_name) + str(random.randint(100, 999))
        if username_sel:
            await page.locator(username_sel).first.fill(ctx.username)
            await _human_delay(0.5, 1)
            if next_btn:
                await page.locator(next_btn).first.click()
            else:
                await page.keyboard.press("Enter")
            await _human_delay(3, 5)

    ctx.email = f"{ctx.username}@gmail.com"
    ctx._log(f"Email will be: {ctx.email}")


async def step_5_password(page, ctx: RegContext):
    """Step 5: Enter password + confirm password and click Next."""
    await block_check(page, ctx.provider, ctx, "password")

    ctx._log("Entering password...")
    pwd_sel = await _wait_and_find(page, [
        'input[name="Passwd"]', 'input[type="password"]', '#passwd',
        'input[aria-label*="assword"]', 'input[aria-label*="арол"]',
        'input[placeholder*="assword"]', 'input[autocomplete="new-password"]',
    ], "gmail_password", ctx.username, ctx._log, ctx._err, timeout=20000)
    if not pwd_sel:
        raise RecoverableError("E103", "Password field not found")

    await page.locator(pwd_sel).first.click()
    await _human_delay(0.3, 0.6)
    for char in ctx.password:
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
        for char in ctx.password:
            await page.locator(confirm_sel).first.type(char, delay=random.randint(40, 90))

    await _human_delay(0.5, 1)
    next_btn = await _wait_for_any(page, ['button:has-text("Next")'], timeout=5000)
    if next_btn:
        await page.locator(next_btn).first.click()
    else:
        await page.keyboard.press("Enter")
    await _human_delay(3, 5)


async def step_6_sms_verification(page, ctx: RegContext, sms_provider, proxy,
                                   BIRTH_CANCEL_EVENT):
    """Step 6: Phone verification via SMS. May be skippable."""
    ctx._log("Checking SMS verification...")

    # Check for Skip option
    skip_phone = await _wait_for_any(page, [
        'button:has-text("Skip")', 'button:has-text("Пропустить")',
        'a:has-text("Skip")', 'span:has-text("Skip")',
        'div[role="button"]:has-text("Skip")',
    ], timeout=3000)
    if skip_phone:
        ctx._log("[OK] Google offers to skip SMS - skipping!")
        await page.locator(skip_phone).first.click()
        await _human_delay(2, 4)
        return

    phone_sel = await _wait_for_any(page, [
        'input[type="tel"]', 'input[name="phoneNumber"]', '#phoneNumberId',
        'input[aria-label*="hone"]', 'input[aria-label*="елефон"]',
        'input[placeholder*="hone"]', 'input[autocomplete="tel"]',
    ], timeout=10000)

    if not phone_sel:
        ctx._log("SMS not required (good trust score!)")
        return

    if not sms_provider:
        raise FatalError("E502", "Google requires SMS but no SMS provider configured")

    ctx._log("Ordering number for Gmail SMS...")
    from ...services.geo_resolver import resolve_proxy_geo, get_sms_countries_priority
    proxy_geo = resolve_proxy_geo(proxy) if proxy else None

    order, active_sms_provider, expanded_countries = await order_sms_with_chain(
        service="gmail",
        sms_provider=sms_provider,
        proxy_geo=proxy_geo,
        page=None,
        scrape_dropdown=False,
        _log=ctx._log,
        _err=ctx._err,
    )
    if not order:
        raise RecoverableError("E106", "Failed to order SMS number")

    sms_provider = active_sms_provider
    _cls = type(active_sms_provider).__name__.lower()
    if 'grizzly' in _cls:
        _current_sms_provider_name = 'grizzly'
    elif 'fivesim' in _cls or '5sim' in _cls:
        _current_sms_provider_name = '5sim'
    else:
        _current_sms_provider_name = 'simsms'

    phone_number = order["number"]
    order_id = order["id"]
    ctx._log(f"Number: {phone_number}")

    # SMS retry loop
    sms_verified = False
    max_sms_retries = 9

    for sms_attempt in range(max_sms_retries):
        if sms_attempt > 0:
            ctx._log(f"SMS attempt #{sms_attempt + 1}...")

        display_phone = phone_number if phone_number.startswith("+") else f"+{phone_number}"
        await page.locator(phone_sel).first.click()
        await _human_delay(0.3, 0.6)
        await page.locator(phone_sel).first.fill(display_phone)
        await _human_delay(0.5, 1)

        send_btn = await _wait_for_any(page, [
            'button:has-text("Next")', '#next button'
        ], timeout=5000)
        if send_btn:
            await page.locator(send_btn).first.click()
        else:
            await page.keyboard.press("Enter")
        await _human_delay(3, 5)

        # Check if Google rejected the number
        is_rejected = False
        try:
            page_text = await page.locator('body').inner_text()
            rejection_phrases = [
                "phone number can't be used", "couldn't verify",
                "not a valid phone", "invalid phone",
                "try a different number", "this number cannot be used",
                "not supported",
            ]
            is_rejected = any(p.lower() in page_text.lower() for p in rejection_phrases)
        except Exception:
            pass

        if is_rejected:
            ctx._log(f"Google rejected number {display_phone} — getting new one via chain")
            try:
                await asyncio.to_thread(sms_provider.cancel_number, order_id)
            except Exception:
                pass

            new_order, new_provider, new_provider_name = await get_next_sms_number(
                service="gmail",
                current_provider=sms_provider,
                current_provider_name=_current_sms_provider_name or 'simsms',
                expanded_countries=expanded_countries,
                _log=ctx._log,
                _err=ctx._err,
            )
            if not new_order:
                raise RecoverableError("E107", "All SMS providers exhausted for Gmail")
            if new_provider:
                sms_provider = new_provider
                _current_sms_provider_name = new_provider_name
            phone_number = new_order["number"]
            order_id = new_order["id"]
            ctx._log(f"New number: {phone_number}")

            phone_sel = await _wait_for_any(page, [
                'input[type="tel"]', 'input[name="phoneNumber"]', '#phoneNumberId',
            ], timeout=5000)
            if not phone_sel:
                raise RecoverableError("E108", "Phone field disappeared after rejection")
            continue

        # Phone accepted — wait for code
        try:
            if hasattr(sms_provider, 'set_status'):
                await asyncio.to_thread(sms_provider.set_status, order_id, 1)
        except Exception:
            pass

        ctx._log(f"Waiting for SMS code ({SMS_CODE_TIMEOUT}s timeout)...")
        sms_result = await asyncio.to_thread(
            sms_provider.get_sms_code, order_id, SMS_CODE_TIMEOUT, BIRTH_CANCEL_EVENT
        )

        sms_code = None
        if isinstance(sms_result, dict):
            sms_code = sms_result.get("code")
            if sms_result.get("error"):
                ctx._log(f"SMS error: {sms_result['error']}")
        elif isinstance(sms_result, str):
            sms_code = sms_result

        if not sms_code:
            ctx._log(f"SMS code not received in {SMS_CODE_TIMEOUT}s — trying next number")
            try:
                await asyncio.to_thread(sms_provider.cancel_number, order_id)
            except Exception:
                pass

            new_order, new_provider, new_provider_name = await get_next_sms_number(
                service="gmail",
                current_provider=sms_provider,
                current_provider_name=_current_sms_provider_name or 'simsms',
                expanded_countries=expanded_countries,
                _log=ctx._log,
                _err=ctx._err,
            )
            if not new_order:
                raise RecoverableError("E109", "All SMS providers exhausted for Gmail")
            if new_provider:
                sms_provider = new_provider
                _current_sms_provider_name = new_provider_name
            phone_number = new_order["number"]
            order_id = new_order["id"]
            ctx._log(f"New number: {phone_number}")

            phone_sel = await _wait_for_any(page, [
                'input[type="tel"]', 'input[name="phoneNumber"]', '#phoneNumberId',
            ], timeout=5000)
            if not phone_sel:
                try:
                    await page.go_back()
                    await _human_delay(2, 3)
                    phone_sel = await _wait_for_any(page, [
                        'input[type="tel"]', 'input[name="phoneNumber"]',
                    ], timeout=5000)
                except Exception:
                    pass
            if not phone_sel:
                raise RecoverableError("E110", "Cannot get back to phone entry for retry")
            continue

        # Got SMS code!
        ctx._log(f"SMS code: {sms_code}")
        code_sel = await _wait_for_any(page, [
            'input[type="tel"]', 'input[name="code"]', '#code'
        ], timeout=15000)
        if code_sel:
            await page.locator(code_sel).first.fill(sms_code)
            await _human_delay(0.5, 1)
            verify_btn = await _wait_for_any(page, [
                'button:has-text("Verify")', 'button:has-text("Подтвердить")',
                'button:has-text("Next")'
            ], timeout=5000)
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

        sms_verified = True
        break

    if not sms_verified:
        raise RecoverableError("E111", "Failed to verify SMS after all attempts")

    await _human_delay(3, 5)


async def step_7_recovery_skip(page, ctx: RegContext):
    """Step 7: Skip recovery email/phone prompt if shown."""
    recovery_skip = await _wait_for_any(page, [
        'button:has-text("Skip")', 'button:has-text("Пропустить")',
        'a:has-text("Skip")', 'span:has-text("Skip")',
        'div[role="button"]:has-text("Skip")',
    ], timeout=3000)
    if recovery_skip:
        ctx._log("Skipping recovery email/phone...")
        await page.locator(recovery_skip).first.click()
        await _human_delay(2, 4)


async def step_8_accept_tos(page, ctx: RegContext):
    """Step 8: Accept Terms of Service."""
    ctx._log("Accepting terms...")
    agree_btn = await _wait_for_any(page, [
        'button:has-text("I agree")', 'button:has-text("Принимаю")',
        'button:has-text("Agree")', 'button:has-text("Next")',
    ], timeout=10000)
    if agree_btn:
        await page.locator(agree_btn).first.click()
        await _human_delay(3, 5)


async def step_9_verify_success(page, ctx: RegContext) -> bool:
    """Step 9: Verify registration succeeded by checking URL."""
    final_url = page.url.lower()
    ctx._log(f"Final URL: {final_url}")

    success_indicators = [
        "myaccount.google.com", "mail.google.com",
        "/speedbump", "/interstitial", "/signinchooser"
    ]
    if any(ind in final_url for ind in success_indicators):
        ctx._log("[OK] URL confirms successful registration")
        return True
    elif "accounts.google.com/signup" not in final_url:
        ctx._log("[OK] Left registration page")
        return True
    else:
        ctx._err(f"[FAIL] Registration not confirmed - URL: {final_url}")
        await _debug_screenshot(page, "gmail_not_confirmed")
        raise FatalError("E503", f"Registration not confirmed: {final_url}")


# ── Main Orchestrator ────────────────────────────────────────────────────────────


async def register_single_gmail(
    browser_manager: BrowserManager,
    proxy: Proxy | None,
    name_pool: list,
    captcha_provider: CaptchaProvider | None,
    sms_provider,
    db: Session,
    thread_log: ThreadLog | None = None,
    ACTIVE_PAGES: dict = None,
    BIRTH_CANCEL_EVENT: threading.Event = None,
) -> Account | None:
    """Register a single Gmail account using the Defensive Coding Template."""
    if ACTIVE_PAGES is None:
        ACTIVE_PAGES = {}
    if BIRTH_CANCEL_EVENT is None:
        BIRTH_CANCEL_EVENT = threading.Event()
    if not name_pool:
        logger.error("[Gmail] [FAIL] No names! Load a name pack before registration.")
        if thread_log:
            thread_log.status = "error"
            thread_log.error_message = "No names! Load a name pack."
            try: db.commit()
            except: pass
        return None

    first_name, last_name = random.choice(name_pool)
    password = generate_password()
    username = generate_username(first_name, last_name)

    # ── Create RegContext ──
    def _log(msg: str):
        n = getattr(thread_log, '_worker_id', 0) + 1 if thread_log else '?'
        logger.info(f"[Gmail][Thread {n}] {msg}")
        if thread_log:
            thread_log.current_action = f"Thread {n}: {msg}"
            try: db.commit()
            except Exception: pass

    def _err(msg: str):
        n = getattr(thread_log, '_worker_id', 0) + 1 if thread_log else '?'
        logger.error(f"[Gmail][Thread {n}] {msg}")
        if thread_log:
            thread_log.error_message = f"Thread {n}: {msg}"[:500]
            try: db.commit()
            except Exception: pass

    ctx = RegContext(
        provider="gmail",
        username=username,
        password=password,
        email=f"{username}@gmail.com",
        first_name=first_name,
        last_name=last_name,
        proxy_ip=f"{proxy.host}:{proxy.port}" if proxy else "",
        proxy_geo=getattr(proxy, 'country', '') or "" if proxy else "",
        proxy_type=getattr(proxy, 'proxy_type', '') or "" if proxy else "",
        thread_id=thread_log.id if thread_log else 0,
        _log=_log,
        _err=_err,
    )

    # ── Initialize Vision Engine ──
    vision = None
    try:
        from ..vision import VisionEngine
        vision = VisionEngine("gmail", debug=True)
        _log("[Vision] Vision Engine active")
    except Exception as ve:
        logger.debug(f"[Gmail] Vision not available: {ve}")

    context = await browser_manager.create_context(proxy=proxy, geo=None)

    try:
        reset_chain_state("gmail")
        page = await context.new_page()
        ACTIVE_PAGES[ctx.thread_id] = {"page": page, "context": context}

        # ── Execute Steps ──
        await step_0_warmup(page, ctx)

        await step_1_navigate(page, ctx, proxy, db)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        await step_2_name(page, ctx, captcha_provider)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        await step_3_birthday_gender(page, ctx)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        await step_4_username(page, ctx)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        await step_5_password(page, ctx)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        await step_6_sms_verification(page, ctx, sms_provider, proxy, BIRTH_CANCEL_EVENT)

        await step_7_recovery_skip(page, ctx)

        await step_8_accept_tos(page, ctx)

        await step_9_verify_success(page, ctx)

        # ── Save session and create account ──
        birthday = getattr(ctx, '_birthday', generate_birthday())
        gender = getattr(ctx, '_gender', 'random')

        try:
            session_path = await browser_manager.save_session(context, 0)
        except Exception:
            session_path = None

        account = Account(
            email=ctx.email,
            password=ctx.password,
            provider="gmail",
            first_name=ctx.first_name,
            last_name=ctx.last_name,
            gender=gender,
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

        logger.info(f"[OK] Gmail registered: {ctx.email}")
        export_account_to_file(account)

        # IMAP verification (non-blocking)
        try:
            from ...services.imap_checker import verify_account_imap
            await verify_account_imap(account, db, _log, _err)
        except Exception as imap_e:
            logger.debug(f"[Gmail] IMAP check skipped: {imap_e}")

        # Post-registration warmup
        try:
            from ..human_behavior import post_registration_warmup
            _log("[OK] Post-reg session warmup...")
            await post_registration_warmup(page, provider="gmail")
        except Exception as warmup_e:
            logger.debug(f"[Gmail] Post-reg warmup error: {warmup_e}")

        return account

    except (RateLimitError, BannedIPError, CaptchaFailError, FatalError, RecoverableError):
        raise
    except Exception as e:
        logger.error(f"[FAIL] Gmail registration failed: {e}", exc_info=True)
        _err(str(e)[:500])
        raise FatalError("E599", f"Unhandled: {str(e)[:200]}")
    finally:
        ACTIVE_PAGES.pop(ctx.thread_id, None)
        try:
            await context.close()
        except Exception:
            pass
