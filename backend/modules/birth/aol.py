"""
Leomail v4 - AOL Registration Engine (Defensive Coding Template)
Registers aol.com accounts via login.aol.com/account/create.
Flow: signup -> fill form (name+email+password+birthday) -> submit -> SMS phone page -> verify code -> done
AOL = Yahoo/Verizon family. Requires SMS. Has FunCaptcha/reCAPTCHA after phone submission.
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
    detect_and_solve_funcaptcha as _detect_and_solve_funcaptcha,
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


# ── Helpers ──────────────────────────────────────────────────────────────────────


async def _check_error_page(page, context_msg=""):
    """Quick check for AOL error/block pages. Returns error string or None."""
    url = page.url or ""
    error_urls = ["/error", "challenge/fail", "challenge/recaptcha", "/blocked",
                  "guce.yahoo", "consent.yahoo", "/sorry"]
    for pattern in error_urls:
        if pattern in url.lower():
            return f"Error URL detected: {url}"
    try:
        error_text = await page.evaluate("""() => {
            const body = document.body?.innerText?.substring(0, 2000) || '';
            const lc = body.toLowerCase();
            const errors = [
                'something went wrong', 'try again later', 'suspicious activity',
                'temporarily unavailable', 'too many attempts', 'access denied',
                'unable to process', 'service unavailable', 'error 500',
                'we are unable', 'blocked', 'not available in your region'
            ];
            for (const e of errors) {
                if (lc.includes(e)) return body.substring(0, 300);
            }
            return null;
        }""")
        if error_text:
            return f"Error page text: {error_text[:200]}"
    except Exception:
        pass
    return None


# ── Step Functions ───────────────────────────────────────────────────────────────


async def step_0_warmup(page, ctx: RegContext):
    """Step 0: Quick warmup — single Google visit."""
    ctx._log("Quick session warmup...")
    try:
        await page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=15000)
        await _human_delay(1, 2)
        await random_mouse_move(page, steps=2)
    except Exception:
        pass


async def step_1_navigate(page, ctx: RegContext, proxy, db):
    """Step 1: Navigate to AOL signup. Checks: dead proxy, error page, block signals."""
    ctx._log("Opening AOL registration page...")
    try:
        await page.goto(
            "https://login.aol.com/account/create",
            wait_until="domcontentloaded",
            timeout=60000,
        )
    except Exception as nav_e:
        logger.warning(f"[AOL] Navigation error: {nav_e}")

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

    # Check AOL error page
    if "/account/create/error" in current_url or "error" in current_url.split("?")[0].split("/")[-1:]:
        ctx._err(f"[ERR] AOL returned error page - IP blocked or rate limited (URL: {current_url})")
        raise BannedIPError("E301", f"AOL error page: {current_url}")

    # Block scan
    await block_check(page, ctx.provider, ctx, "navigate")

    await random_mouse_move(page, steps=3)
    ctx._log(f"Page: {page.url}")


async def step_2_fill_form(page, ctx: RegContext, birthday):
    """Step 2: Fill all form fields (name, email, password, birthday). AOL has everything on one page."""
    # Fast error check
    error = await _check_error_page(page, "before firstname")
    if error:
        ctx._err(f"[ERR] AOL error before form: {error}")
        raise BannedIPError("E303", f"AOL error before form: {error[:100]}")

    await block_check(page, ctx.provider, ctx, "fill_form")

    ctx._log(f"Entering data: {ctx.first_name} {ctx.last_name} / {ctx.username}")

    # First name
    fn_sel = await _wait_and_find(page, [
        'input[name="firstName"]', '#usernamereg-firstName',
        'input[aria-label*="irst"]', 'input[aria-label*="имя"]',
        'input[placeholder*="First"]', 'input[placeholder*="имя"]',
        'input[autocomplete="given-name"]',
    ], "aol_firstname", ctx.username, ctx._log, ctx._err, timeout=20000)
    if not fn_sel:
        raise RecoverableError("E101", "First name field not found")

    await _human_fill(page, fn_sel, ctx.first_name)
    await _human_delay(1.0, 2.5)

    # Last name
    ln_sel = await _wait_for_any(page, [
        'input[name="lastName"]', '#usernamereg-lastName',
        'input[aria-label*="ast"]', 'input[aria-label*="фам"]',
        'input[placeholder*="Last"]', 'input[placeholder*="фам"]',
        'input[autocomplete="family-name"]',
    ], timeout=5000)
    if ln_sel:
        await _human_fill(page, ln_sel, ctx.last_name)
        await _human_delay(1.2, 2.8)

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
        await _human_fill(page, email_sel, ctx.username)
        await _human_delay(1.5, 3.0)

    # Password
    pwd_sel = await _wait_for_any(page, [
        'input[name="password"]', '#usernamereg-password', 'input[type="password"]',
        'input[aria-label*="assword"]', 'input[aria-label*="арол"]',
        'input[placeholder*="assword"]',
    ], timeout=5000)
    if pwd_sel:
        await _human_fill(page, pwd_sel, ctx.password)
        await _human_delay(1.0, 2.0)

    # Birthday
    await page.mouse.wheel(0, random.randint(30, 80))
    await _human_delay(0.5, 1.0)

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

    await _human_delay(1.5, 3.0)


async def step_3_submit_form(page, ctx: RegContext, captcha_provider):
    """Step 3: Submit form. Handles email-taken retry (up to 3 times)."""
    await page.mouse.wheel(0, random.randint(100, 200))
    await _human_delay(0.8, 1.5)

    ctx._log("Submitting form (Next)...")
    submit_btn = await _wait_for_any(page, [
        'button[name="signup"]',
        'button:has-text("Next")',
        'button[type="submit"]', '#reg-submit-button',
        'button:has-text("Continue")', 'button:has-text("Продолжить")',
        '#usernamereg-submitBtn',
    ], timeout=5000)
    if submit_btn:
        try:
            await page.locator(submit_btn).first.wait_for(state="attached", timeout=3000)
            await _human_click(page, submit_btn)
        except Exception:
            ctx._log("Button disabled - trying Enter...")
            await page.keyboard.press("Enter")
    else:
        await page.keyboard.press("Enter")

    await _human_delay(4, 8)

    # Email-taken retry
    for email_retry in range(3):
        try:
            page_text = await page.locator('body').inner_text()
            email_taken_phrases = [
                "email not available", "not available",
                "already taken", "unavailable",
            ]
            email_taken = any(p.lower() in page_text.lower() for p in email_taken_phrases)
        except Exception:
            email_taken = False

        if email_taken:
            old_username = ctx.username
            ctx.username = generate_username(ctx.first_name, ctx.last_name)
            ctx._log(f"[WARN] Email '{old_username}@aol.com' taken! Trying: {ctx.username}")
            email_sel_retry = await _wait_for_any(page, [
                'input[name="yid"]', '#usernamereg-yid', 'input[name="userId"]',
                'input#reg-userId',
            ], timeout=3000)
            if email_sel_retry:
                await page.locator(email_sel_retry).first.fill("")
                await _human_fill(page, email_sel_retry, ctx.username)
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
                raise RecoverableError("E102", "Email field not found for re-entry")
        else:
            break
    else:
        raise RecoverableError("E103", "AOL rejected 3 usernames in a row")

    # Check for reCAPTCHA after submit
    await _detect_and_solve_recaptcha(page, captcha_provider, ctx._log)
    await _human_delay(1, 2)


async def step_4_sms_verification(page, ctx: RegContext, sms_provider, proxy,
                                   captcha_provider, BIRTH_CANCEL_EVENT):
    """Step 4: Full SMS verification flow with country code matching, WhatsApp avoidance, phone retry."""
    phone_page_input = await _wait_for_any(page, [
        'input#reg-phone', 'input[name="phone"]', 'input#phone-number',
        'input[placeholder*="hone"]', 'input[aria-label*="hone"]',
        'input[data-type="phone"]', 'input[autocomplete="tel"]',
    ], timeout=15000)

    if not phone_page_input:
        ctx._log("[WARN] Phone page not found - AOL may not have moved to next step")
        await _debug_screenshot(page, "4_aol_no_phone_page")
        raise RecoverableError("E104", "Phone page not found after form submit")

    ctx._log("Detected 'Add your phone number' page")

    if not sms_provider:
        # Check if ANY SMS provider is configured via chain
        from ._helpers import get_sms_chain
        if not get_sms_chain():
            raise FatalError("E502", "AOL requires SMS but no SMS provider configured (add 5SIM/Grizzly/SimSMS in Settings)")

    # Order SMS
    proxy_geo = getattr(proxy, 'geo', None) if proxy else None
    ctx._log("Ordering number for AOL SMS...")

    order, active_sms_provider, expanded_countries = await order_sms_with_chain(
        service="aol",
        sms_provider=sms_provider,
        proxy_geo=proxy_geo,
        page=page,
        scrape_dropdown=True,
        _log=ctx._log,
        _err=ctx._err,
    )
    if not order:
        raise RecoverableError("E105", "Failed to order SMS number")

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
    sms_country = order.get("country", "")
    ctx._active_sms = {"provider": sms_provider, "order_id": order_id, "number": phone_number}
    display_phone = phone_number if phone_number.startswith("+") else f"+{phone_number}"
    ctx._log(f"Number: {display_phone} (country: {sms_country})")

    # Strip phone prefix for local number
    phone_prefix = PHONE_COUNTRY_MAP.get(sms_country)
    local_number = phone_number.lstrip("+")
    if phone_prefix and local_number.startswith(phone_prefix):
        local_number = local_number[len(phone_prefix):]
        ctx._log(f"Stripped prefix +{phone_prefix}, entering: {local_number}")
    else:
        ctx._log(f"Entering as-is: {local_number}")

    # Change AOL's country code IF it doesn't match
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
        ctx._log(f"AOL shows +{aol_page_prefix}, SMS number +{sms_prefix} - need to change")
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
                ctx._log(f"Country code changed via JS: +{sms_prefix}")
        except Exception:
            pass

        if not country_changed:
            page_country = PREFIX_TO_SMS_COUNTRY.get(aol_page_prefix)
            if page_country:
                ctx._log(f"[WARN] Failed to change +{aol_page_prefix}->+{sms_prefix}. "
                         f"Canceling number and ordering from {page_country}")
                try:
                    await asyncio.to_thread(sms_provider.cancel_order, order_id)
                except Exception:
                    pass
                new_order, new_provider, new_provider_name = await get_next_sms_number(
                    service="aol",
                    current_provider=sms_provider,
                    current_provider_name=_current_sms_provider_name or 'simsms',
                    expanded_countries=[page_country] + [c for c in expanded_countries if c != page_country],
                    _log=ctx._log,
                    _err=ctx._err,
                )
                if new_provider:
                    sms_provider = new_provider
                    _current_sms_provider_name = new_provider_name
                if new_order:
                    phone_number = new_order["number"]
                    order_id = new_order["id"]
                    sms_country = new_order.get("country", page_country)
                    phone_prefix = PHONE_COUNTRY_MAP.get(sms_country)
                    local_number = phone_number.lstrip("+")
                    if phone_prefix and local_number.startswith(phone_prefix):
                        local_number = local_number[len(phone_prefix):]
                    ctx._log(f"[OK] New number for +{aol_page_prefix}: {local_number}")
                else:
                    raise RecoverableError("E106", f"Failed to order number for +{aol_page_prefix}")
            else:
                ctx._log(f"[WARN] Failed to change code, unknown prefix +{aol_page_prefix} - entering full number")
                local_number = f"{sms_prefix}{local_number}"

    # Human-like: read page, scroll
    await random_mouse_move(page, steps=3)
    await _human_delay(3.0, 5.0)
    await page.mouse.wheel(0, random.randint(30, 80))
    await _human_delay(0.8, 1.5)

    # Fill phone number
    try:
        await page.locator(phone_page_input).first.fill("")
        await _human_delay(0.3, 0.5)
    except Exception:
        pass
    await _human_fill(page, phone_page_input, local_number)
    ctx._log(f"Entered number: {local_number}")
    await _human_delay(1.5, 3.0)

    # Click "Get code by text" — NEVER WhatsApp
    # Multi-locale: AOL shows this page in user's proxy language
    await random_mouse_move(page, steps=2)
    await _human_delay(2.0, 4.0)

    sms_button_texts = [
        # English
        'button:has-text("Receive code by text")', 'button:has-text("Get code by text")',
        'button:has-text("code by text")', 'button:has-text("Text me")',
        'button:has-text("Send code")', 'button:has-text("Receive code")',
        # German
        'button:has-text("Code per SMS")', 'button:has-text("SMS erhalten")',
        'button:has-text("Per SMS")',
        # French
        'button:has-text("par SMS")', 'button:has-text("Recevoir par SMS")',
        # Spanish
        'button:has-text("Enviar código")', 'button:has-text("código por SMS")',
        'button:has-text("mensaje de texto")',
        # Portuguese
        'button:has-text("por SMS")',
        # Italian
        'button:has-text("via SMS")', 'button:has-text("Ricevi codice")',
        # Turkish
        'button:has-text("SMS ile")', 'button:has-text("SMS gönder")',
        # Dutch
        'button:has-text("per sms")', 'button:has-text("Ontvang code")',
        # Russian
        'button:has-text("Получить код по SMS")', 'button:has-text("Отправить код")',
    ]
    get_code_btn = await _wait_for_any(page, sms_button_texts, timeout=5000)

    if not get_code_btn:
        ctx._log("[WARN] No SMS button — checking for SMS link...")
        sms_link_selectors = [
            'a:has-text("Receive code by text")', 'a:has-text("code by text")',
            'a:has-text("Text me")', 'a:has-text("Enviar código por texto")',
            'a:has-text("Code per SMS")', 'a:has-text("SMS erhalten")',
            'a:has-text("par SMS")', 'a:has-text("por SMS")',
            'a:has-text("via SMS")', 'a:has-text("per sms")',
            'button:has-text("Receive code")',
        ]
        sms_link = await _wait_for_any(page, sms_link_selectors, timeout=3000)
        if sms_link:
            get_code_btn = sms_link
            ctx._log("[OK] Found SMS as link (below WhatsApp button)")

    if not get_code_btn:
        # Fallback 2: universal SMS keyword on ANY clickable element
        ctx._log("[WARN] SMS button/link not found by locale — trying universal 'SMS' keyword...")
        universal_sms = await _wait_for_any(page, [
            'button:has-text("SMS")', 'a:has-text("SMS")',
            '[role="button"]:has-text("SMS")', 'div:has-text("SMS") >> button',
        ], timeout=3000)
        if universal_sms:
            get_code_btn = universal_sms
            ctx._log("[OK] Found clickable element with 'SMS' text")

    if not get_code_btn:
        # Fallback 3: primary/submit button (SMS is ALWAYS the primary action)
        ctx._log("[WARN] No SMS element found — using primary button...")
        primary_btn = await _wait_for_any(page, [
            'button[type="submit"]', '#send-code-button', 'button[data-type="sms"]',
            'button.primary', 'button[class*="primary"]', 'button[class*="cta"]',
        ], timeout=3000)
        if primary_btn:
            get_code_btn = primary_btn
            ctx._log("[OK] Using primary/submit button")

    if not get_code_btn:
        # Fallback 4: first visible non-WhatsApp button
        ctx._log("[WARN] No primary button — trying first visible button...")
        try:
            all_buttons = page.locator('button:visible')
            btn_count = await all_buttons.count()
            for i in range(btn_count):
                btn_text = (await all_buttons.nth(i).inner_text()).strip().lower()
                if 'whatsapp' not in btn_text and len(btn_text) > 0:
                    get_code_btn = all_buttons.nth(i)
                    ctx._log(f"[OK] Using first non-WhatsApp visible button: '{btn_text[:40]}'")
                    break
        except Exception as e:
            ctx._log(f"[WARN] Button scan failed: {e}")

    if not get_code_btn:
        ctx._log("[WARN] Get code by text button not found - trying Enter")
        await page.keyboard.press("Enter")
        await _human_delay(4, 7)
    else:
        # Phone retry loop
        max_phone_retries = 3
        phone_accepted = False

        for phone_attempt in range(max_phone_retries):
            if phone_attempt > 0:
                ctx._log(f"Attempt #{phone_attempt + 1} with new number...")

            ctx._log("Pressing 'Get code by text'...")
            await _human_click(page, get_code_btn)
            await _human_delay(4, 7)

            # CAPTCHA after clicking 'Get code'
            for captcha_attempt in range(2):
                captcha_solved = await _detect_and_solve_funcaptcha(page, captcha_provider, ctx._log)
                if not captcha_solved:
                    captcha_solved = await _detect_and_solve_recaptcha(page, captcha_provider, ctx._log)
                if captcha_solved:
                    ctx._log(f"CAPTCHA solved after 'Get code' (attempt {captcha_attempt + 1})")
                    await _human_delay(3, 6)
                    try:
                        resubmit = await _wait_for_any(page, [
                            'button[type="submit"]', 'button:has-text("Get code")',
                            'button:has-text("Send code")', 'button:has-text("Continue")',
                            'button:has-text("Verify")',
                        ], timeout=3000)
                        if resubmit:
                            await _human_click(page, resubmit)
                            await _human_delay(4, 7)
                    except Exception:
                        pass
                else:
                    break

            # Check phone rejection
            try:
                page_text = await page.locator('body').inner_text()
                rejection_phrases = [
                    "don't support this number", "doesn't look right",
                    "not a valid phone", "invalid phone",
                    "try another number", "provide another one",
                    "unable to verify this number", "not supported", "invalid number",
                ]
                is_rejected = any(phrase.lower() in page_text.lower() for phrase in rejection_phrases)
            except Exception:
                is_rejected = False

            if not is_rejected:
                curr = page.url
                ctx._log(f"After 'Get code': {curr}")
                if 'challenge/fail' in curr or '/error' in curr:
                    captcha_on_fail = await _detect_and_solve_recaptcha(page, captcha_provider, ctx._log)
                    if captcha_on_fail:
                        ctx._log("CAPTCHA solved on challenge/fail page, trying again...")
                        await _human_delay(3, 5)
                        curr2 = page.url
                        if 'challenge/fail' not in curr2 and '/error' not in curr2:
                            phone_accepted = True
                            break
                    raise BannedIPError("E304", f"AOL blocked: challenge/fail ({curr})")

                try:
                    phone_still_visible = await page.locator(phone_page_input).first.is_visible()
                except Exception:
                    phone_still_visible = False

                if phone_still_visible:
                    ctx._log("[WARN] Phone form still visible - number not accepted, trying another")
                    is_rejected = True
                else:
                    phone_accepted = True
                    break

            # Phone rejected — cancel and get new number
            ctx._log(f"AOL rejected number {display_phone} - getting new one")
            await _debug_screenshot(page, f"aol_phone_rejected_{phone_attempt}")
            try:
                await asyncio.to_thread(sms_provider.cancel_number, order_id)
            except Exception:
                pass

            new_order, new_provider, new_provider_name = await get_next_sms_number(
                service="aol",
                current_provider=sms_provider,
                current_provider_name=_current_sms_provider_name or 'simsms',
                expanded_countries=expanded_countries,
                _log=ctx._log,
                _err=ctx._err,
            )
            if new_provider:
                sms_provider = new_provider
                _current_sms_provider_name = new_provider_name
            if not new_order:
                raise RecoverableError("E107", "SMS error getting new number")

            phone_number = new_order["number"]
            order_id = new_order["id"]
            sms_country = new_order.get("country", sms_country)
            display_phone = phone_number if phone_number.startswith("+") else f"+{phone_number}"
            ctx._log(f"New number: {display_phone} (country: {sms_country})")

            phone_prefix = PHONE_COUNTRY_MAP.get(sms_country, phone_prefix)
            local_number = phone_number.lstrip("+")
            if phone_prefix and local_number.startswith(phone_prefix):
                local_number = local_number[len(phone_prefix):]

            try:
                await page.locator(phone_page_input).first.fill("")
                await _human_delay(0.3, 0.5)
            except Exception:
                pass
            await _human_fill(page, phone_page_input, local_number)
            ctx._log(f"Entered new number: {local_number}")
            await _human_delay(1.5, 3.0)

            get_code_btn = await _wait_for_any(page, [
                'button:has-text("Get code by text")',
                'button:has-text("code by text")',
                'button[type="submit"]',
            ], timeout=3000)
            if not get_code_btn:
                raise RecoverableError("E108", "Get code button not found after number change")

        if not phone_accepted:
            raise RecoverableError("E109", f"AOL rejected {max_phone_retries} numbers in a row")

    # reCAPTCHA after phone submit
    await _detect_and_solve_recaptcha(page, captcha_provider, ctx._log)
    await _human_delay(1, 2)

    # Wait for SMS code
    if order_id:
        try:
            if hasattr(sms_provider, 'set_status'):
                await asyncio.to_thread(sms_provider.set_status, order_id, 1)
        except Exception:
            pass

        ctx._log("Waiting for AOL SMS code...")
        ctx._log(f"Page: {page.url}")

        # Check for challenge/fail redirect
        sms_url = page.url
        if 'challenge/fail' in sms_url or '/error' in sms_url:
            ctx._err(f"AOL redirected to challenge/fail after phone: {sms_url}")
            await _debug_screenshot(page, "aol_challenge_after_phone")
            captcha_solved = await _detect_and_solve_recaptcha(page, captcha_provider, ctx._log)
            if not captcha_solved:
                try:
                    await asyncio.to_thread(sms_provider.cancel_number, order_id)
                except Exception:
                    pass
                raise BannedIPError("E305", f"AOL challenge/fail after phone: {sms_url}")
            await _human_delay(3, 5)

        # Wait for code input fields
        first_digit = await _wait_for_any(page, [
            'input#verify-code-0', 'input[aria-label="Code 1"]',
            'input[name="code"]', 'input[name="verificationCode"]',
            'input[name="verify_code"]', 'input[type="tel"][maxlength="1"]',
            'input[data-type="code"]', 'input.phone-code',
            'input[autocomplete="one-time-code"]',
        ], timeout=30000)

        if first_digit:
            ctx._log(f"[OK] SMS code field found: {first_digit}")
        else:
            ctx._log("[WARN] SMS code field NOT FOUND - AOL did not show verification form!")
            ctx._log(f"Current URL: {page.url}")
            await _debug_screenshot(page, "aol_no_sms_field")

        sms_result = await asyncio.to_thread(sms_provider.get_sms_code, order_id, 300, BIRTH_CANCEL_EVENT)
        sms_code = None
        if isinstance(sms_result, dict):
            sms_code = sms_result.get("code")
            if sms_result.get("error"):
                ctx._err(f"SMS error: {sms_result['error']}")
                try:
                    await asyncio.to_thread(sms_provider.cancel_number, order_id)
                except Exception:
                    pass
                raise RecoverableError("E110", f"SMS error: {sms_result['error']}")
        elif isinstance(sms_result, str):
            sms_code = sms_result

        if not sms_code:
            ctx._err("SMS code not received")
            try:
                await asyncio.to_thread(sms_provider.cancel_number, order_id)
            except Exception:
                pass
            raise RecoverableError("E111", "SMS code not received")

        ctx._log(f"SMS code: {sms_code}")
        code_digits = str(sms_code).strip()
        for i, digit in enumerate(code_digits[:6]):
            digit_sel = f'input#verify-code-{i}'
            try:
                await page.locator(digit_sel).first.fill(digit)
                await _human_delay(0.1, 0.3)
            except Exception:
                if first_digit:
                    await page.locator(first_digit).first.fill(code_digits)
                break
        await _human_delay(0.5, 1)

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

    # Store display_phone for account metadata
    ctx._display_phone = display_phone


async def step_5_verify_success(page, ctx: RegContext) -> bool:
    """Step 5: Verify registration succeeded."""
    ctx.email = f"{ctx.username}@aol.com"
    final_url = page.url
    ctx._log(f"Final URL: {final_url}")

    registration_success = False
    try:
        success_indicators_url = [
            "mail.aol.com", "aol.com/welcome",
            "account/create/success", "/welcome",
            "/myaccount", "/manage_account",
        ]
        if any(ind in final_url.lower() for ind in success_indicators_url):
            registration_success = True
            ctx._log("[OK] URL confirms successful registration")

        if not registration_success:
            on_create = "/account/create" in final_url
            on_success = "/account/create/success" in final_url
            if not on_create or on_success:
                registration_success = True
                ctx._log("[OK] Left registration page - counting as success")

        if registration_success:
            page_text = await page.locator('body').inner_text()
            fail_indicators = ["registration failed", "account could not be created"]
            if any(fi.lower() in page_text.lower() for fi in fail_indicators):
                registration_success = False
                ctx._err("[FAIL] Page contains registration error indicators")
    except Exception as e:
        ctx._log(f"Success check: error ({e}), counting as success if URL changed")
        on_create = "/account/create" in final_url
        on_success = "/account/create/success" in final_url
        if not on_create or on_success:
            registration_success = True

    if not registration_success:
        ctx._err(f"[FAIL] Registration NOT confirmed! URL: {final_url}")
        await _debug_screenshot(page, "aol_registration_not_confirmed")
        raise FatalError("E504", f"Registration not confirmed: {final_url}")

    return True


# ── Main Orchestrator ────────────────────────────────────────────────────────────


async def register_single_aol(
    browser_manager: BrowserManager,
    proxy: Proxy | None,
    name_pool: list,
    sms_provider,
    db: Session,
    thread_log: ThreadLog | None = None,
    captcha_provider: CaptchaProvider | None = None,
    ACTIVE_PAGES: dict = None,
    BIRTH_CANCEL_EVENT: threading.Event = None,
) -> Account | None:
    """Register a single AOL account using the Defensive Coding Template."""
    if ACTIVE_PAGES is None:
        ACTIVE_PAGES = {}
    if BIRTH_CANCEL_EVENT is None:
        BIRTH_CANCEL_EVENT = threading.Event()
    if not name_pool:
        logger.error("[AOL] [FAIL] No names! Load a name pack before registration.")
        if thread_log:
            thread_log.status = "error"
            thread_log.error_message = "No names! Load a name pack."
            try: db.commit()
            except: pass
        return None

    first_name, last_name = random.choice(name_pool)
    password = generate_password()
    username = generate_username(first_name, last_name)
    birthday = generate_birthday()

    # ── Create RegContext ──
    def _log(msg: str):
        n = getattr(thread_log, '_worker_id', 0) + 1 if thread_log else '?'
        logger.info(f"[AOL][Thread {n}] {msg}")
        if thread_log:
            thread_log.current_action = f"Thread {n}: {msg}"
            try: db.commit()
            except Exception: pass

    def _err(msg: str):
        n = getattr(thread_log, '_worker_id', 0) + 1 if thread_log else '?'
        logger.error(f"[AOL][Thread {n}] {msg}")
        if thread_log:
            thread_log.error_message = f"Thread {n}: {msg}"[:500]
            try: db.commit()
            except Exception: pass

    ctx = RegContext(
        provider="aol",
        username=username,
        password=password,
        email=f"{username}@aol.com",
        first_name=first_name,
        last_name=last_name,
        proxy_ip=f"{proxy.host}:{proxy.port}" if proxy else "",
        proxy_geo=getattr(proxy, 'country', '') or "" if proxy else "",
        proxy_type=getattr(proxy, 'proxy_type', '') or "" if proxy else "",
        thread_id=thread_log.id if thread_log else 0,
        _log=_log,
        _err=_err,
    )

    # Initialize Vision Engine
    vision = None
    try:
        from ..vision import VisionEngine
        vision = VisionEngine("aol", debug=True)
        _log("[Vision] Vision Engine active")
    except Exception as ve:
        logger.debug(f"[AOL] Vision not available: {ve}")

    ctx._active_sms = None
    _sms_success = False
    reset_chain_state("aol")

    context = await browser_manager.create_context(proxy=proxy, geo=None)

    try:
        page = await context.new_page()
        ACTIVE_PAGES[ctx.thread_id] = {"page": page, "context": context}

        # ── Execute Steps ──
        await step_0_warmup(page, ctx)

        await step_1_navigate(page, ctx, proxy, db)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        await step_2_fill_form(page, ctx, birthday)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        await step_3_submit_form(page, ctx, captcha_provider)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        await step_4_sms_verification(page, ctx, sms_provider, proxy,
                                       captcha_provider, BIRTH_CANCEL_EVENT)

        await step_5_verify_success(page, ctx)

        # ── Save session and create account ──
        try:
            session_path = await browser_manager.save_session(context, 0)
        except Exception:
            session_path = None

        _sms_success = True
        display_phone = getattr(ctx, '_display_phone', '')

        account = Account(
            email=ctx.email,
            password=ctx.password,
            provider="aol",
            first_name=ctx.first_name,
            last_name=ctx.last_name,
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

        logger.info(f"[OK] AOL registered: {ctx.email}")
        export_account_to_file(account, {"sms_phone": display_phone})

        # IMAP verification (non-blocking)
        try:
            from ...services.imap_checker import verify_account_imap
            await verify_account_imap(account, db, _log, _err)
        except Exception as imap_e:
            logger.debug(f"[AOL] IMAP check skipped: {imap_e}")

        # Post-registration warmup
        try:
            from ..human_behavior import post_registration_warmup
            _log("[OK] Post-reg session warmup...")
            await post_registration_warmup(page, provider="aol")
        except Exception as warmup_e:
            logger.debug(f"[AOL] Post-reg warmup error: {warmup_e}")

        return account

    except (RateLimitError, BannedIPError, CaptchaFailError, FatalError, RecoverableError):
        raise
    except Exception as e:
        logger.error(f"[FAIL] AOL registration failed: {e}", exc_info=True)
        _err(str(e)[:500])
        raise FatalError("E599", f"Unhandled: {str(e)[:200]}")
    finally:
        if ctx._active_sms and not _sms_success:
            try:
                await asyncio.to_thread(ctx._active_sms["provider"].cancel_order, ctx._active_sms["order_id"])
                logger.info(f"[AOL] [WARN] SMS cancelled (crash recovery): {ctx._active_sms['number']}")
            except Exception:
                pass
        ACTIVE_PAGES.pop(ctx.thread_id, None)
        try:
            await context.close()
        except Exception:
            pass
