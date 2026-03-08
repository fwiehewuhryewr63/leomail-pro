"""
Leomail v4 - Yahoo Registration Engine (Defensive Coding Template)
Registers yahoo.com accounts via login.yahoo.com/account/create.
Flow: signup -> fill form (name+email+password+birthday) -> submit -> SMS phone page -> verify code -> done
Yahoo = Verizon family. Requires SMS. Has FunCaptcha/reCAPTCHA. Vision Engine support.
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
    idle_behavior, form_review_scan, focus_blur_field, reading_dwell,
)
from ._helpers import (
    human_delay as _human_delay,
    human_fill as _human_fill,
    human_type as _human_type,
    human_click as _human_click,
    check_error_on_page as _check_error_on_page,
    fluent_combobox_select as _fluent_combobox_select,
    wait_for_any as _wait_for_any,
    detect_and_solve_funcaptcha as _detect_and_solve_funcaptcha,
    detect_and_solve_recaptcha as _detect_and_solve_recaptcha,
    debug_screenshot as _debug_screenshot,
    _safe_screenshot,
    order_sms_with_chain, get_next_sms_number, get_sms_chain,
    reset_chain_state,
    PHONE_COUNTRY_MAP, PREFIX_TO_SMS_COUNTRY, COUNTRY_TO_ISO2,
    RecoverableError, RateLimitError, BannedIPError, CaptchaFailError, FatalError,
    RegContext, verify_page_state, block_check, run_step, export_account_to_file,
    get_expected_language,
    run_flow_machine,
)


# ── Helpers ──────────────────────────────────────────────────────────────────────


async def _check_error_page(page, context_msg=""):
    """Quick check for Yahoo error/block pages. Returns error string or None.
    Requires 2+ keyword matches to avoid false positives from normal page text."""
    url = page.url or ""
    error_urls = ["/error", "challenge/fail", "challenge/recaptcha", "/blocked",
                  "guce.yahoo", "/sorry"]
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
                'we are unable', 'not available in your region'
            ];
            let matchCount = 0;
            for (const e of errors) {
                if (lc.includes(e)) matchCount++;
            }
            // Require 2+ matches to avoid false positives from normal page text
            if (matchCount >= 2) return body.substring(0, 300);
            return null;
        }""")
        if error_text:
            return f"Error page text: {error_text[:200]}"
    except Exception:
        pass
    return None


# ── Step Functions ───────────────────────────────────────────────────────────────


async def step_0_warmup(page, ctx: RegContext):
    """Step 0: Full pre-registration warmup — browse sites, build session, then Yahoo cookies."""
    ctx._log("Full session warmup (browsing + Yahoo cookies)...")

    # Phase 1: Browse 3-6 random sites to build realistic session history
    try:
        geo = ctx.proxy_geo or None
        await warmup_browsing(page, duration_seconds=random.randint(20, 40), geo=geo)
        ctx._log("[Warmup] Browsing warmup complete")
    except Exception as e:
        ctx._log(f"[Warmup] Browsing partial: {e}")

    # Phase 2: Visit yahoo.com to build domain cookies
    try:
        await page.goto("https://www.yahoo.com", wait_until="domcontentloaded", timeout=20000)
        await _human_delay(2, 4)
        # Accept consent/cookies popup
        try:
            consent_btn = page.locator(
                "button:has-text('Accept'), button:has-text('Agree'), "
                "button:has-text('OK'), button[name='agree'], "
                "button:has-text('Akzeptieren'), button:has-text('Accepter'), "
                "button:has-text('Aceptar')"
            ).first
            if await consent_btn.is_visible(timeout=3000):
                await consent_btn.click()
                await _human_delay(1, 2)
        except Exception:
            pass
        # Read Yahoo homepage like a real user
        await reading_dwell(page, min_seconds=3, max_seconds=6)
        await random_scroll(page, direction="down")
        await idle_behavior(page, duration_seconds=random.uniform(2, 4))
        await random_mouse_move(page, steps=3)
        await random_scroll(page, direction="down")
        await _human_delay(1, 3)
    except Exception as warmup_err:
        ctx._log(f"Warmup partial: {warmup_err}")
        try:
            await page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=15000)
            await _human_delay(1, 2)
        except Exception:
            pass


async def step_1_navigate(page, ctx: RegContext, proxy, db, vision=None):
    """Step 1: Navigate to Yahoo signup. Checks: dead proxy, error page, block signals, Vision."""
    ctx._log("Opening Yahoo registration page...")
    try:
        await page.goto(
            "https://login.yahoo.com/account/create",
            wait_until="domcontentloaded",
            timeout=60000,
        )
    except Exception as nav_e:
        logger.warning(f"[Yahoo] Navigation error: {nav_e}")

    await _human_delay(2, 4)

    current_url = page.url or ""
    if "chrome-error" in current_url or "about:blank" == current_url:
        if proxy:
            try:
                proxy.fail_count = (proxy.fail_count or 0) + 1
                if proxy.fail_count >= 3:
                    proxy.status = ProxyStatus.DEAD
                    logger.warning(f"Proxy marked DEAD after {proxy.fail_count} consecutive failures: {proxy.host}:{proxy.port}")
                else:
                    logger.info(f"Proxy temp fail #{proxy.fail_count}/3: {proxy.host}:{proxy.port} (will retry with different proxy)")
                db.commit()
            except Exception:
                pass
        ctx._err(f"[ERR] Proxy navigation failed (URL: {current_url})")
        raise RecoverableError("E501", f"Proxy navigation failed: {current_url}")

    if "/account/create/error" in current_url or "error" in current_url.split("?")[0].split("/")[-1:]:
        ctx._err(f"[ERR] Yahoo returned error page (URL: {current_url})")
        raise BannedIPError("E301", f"Yahoo error page: {current_url}")

    await block_check(page, ctx.provider, ctx, "navigate")

    await random_mouse_move(page, steps=3)
    ctx._log(f"Page: {page.url}")

    if vision:
        try:
            stage = await vision.analyze(page)
            ctx._log(f"[Vision] Stage: {stage['stage']} ({stage['confidence']:.0%}) - {stage['description']}")
            err = await vision.is_error(page)
            if err:
                # Only throw E304 if confidence is meaningful (>40%)
                # Low confidence (20%) = likely false positive from single keyword like "blocked"
                if stage['confidence'] > 0.40:
                    ctx._err(f"[Vision] Error detected: {err['type']} - {err['text']} (confidence: {stage['confidence']:.0%})")
                    raise BannedIPError("E304", f"Vision: {err['type']}: {err['text']}")
                else:
                    ctx._log(f"[Vision] Low-confidence error ({stage['confidence']:.0%}) - ignoring: {err['type']}")
        except (BannedIPError, RateLimitError, FatalError):
            raise
        except Exception as ve:
            logger.debug(f"[Yahoo] Vision stage detect: {ve}")


async def step_2_fill_form(page, ctx: RegContext, birthday):
    """Step 2: Fill all form fields (name, email, password, birthday). Yahoo has everything on one page."""
    error = await _check_error_page(page, "before firstname")
    if error:
        # E303 can be transient — try one reload before aborting
        ctx._log(f"[WARN] Yahoo error before form, trying reload: {error[:80]}")
        try:
            await page.reload(wait_until="domcontentloaded", timeout=15000)
            await _human_delay(3, 5)
            error2 = await _check_error_page(page, "after reload")
            if error2:
                ctx._err(f"[ERR] Yahoo error persists after reload: {error2}")
                raise BannedIPError("E303", f"Yahoo error before form: {error2[:100]}")
            else:
                ctx._log("[OK] Error cleared after reload — continuing")
        except BannedIPError:
            raise
        except Exception:
            ctx._err(f"[ERR] Yahoo error before form: {error}")
            raise BannedIPError("E303", f"Yahoo error before form: {error[:100]}")

    await block_check(page, ctx.provider, ctx, "fill_form")

    ctx._log(f"Entering data: {ctx.first_name} {ctx.last_name} / {ctx.username}")

    # First name
    fn_sel = await _wait_and_find(page, [
        '#reg-firstName', 'input[name="firstName"]', '#usernamereg-firstName',
        'input[aria-label*="irst"]', 'input[aria-label*="имя"]',
        'input[placeholder*="First"]', 'input[placeholder*="имя"]',
        'input[autocomplete="given-name"]',
    ], "yahoo_firstname", ctx.username, ctx._log, ctx._err, timeout=20000)
    if not fn_sel:
        raise RecoverableError("E101", "First name field not found")

    await focus_blur_field(page, fn_sel)
    await _human_fill(page, fn_sel, ctx.first_name)
    await _human_delay(1.5, 3.5)

    # Natural transition between fields
    await between_steps(page)

    # Last name
    ln_sel = await _wait_for_any(page, [
        '#reg-lastName', 'input[name="lastName"]', '#usernamereg-lastName',
        'input[aria-label*="ast"]', 'input[aria-label*="фам"]',
        'input[placeholder*="Last"]', 'input[placeholder*="фам"]',
        'input[autocomplete="family-name"]',
    ], timeout=5000)
    if ln_sel:
        await focus_blur_field(page, ln_sel)
        await _human_fill(page, ln_sel, ctx.last_name)
        await _human_delay(1.5, 3.0)

    # Human thinks about what to type next
    await idle_behavior(page, duration_seconds=random.uniform(1.5, 3.0))
    await page.mouse.wheel(0, random.randint(50, 150))
    await _human_delay(0.5, 1.0)

    await between_steps(page)

    # Email / Username
    email_sel = await _wait_for_any(page, [
        '#reg-userId', 'input[name="userId"]',
        'input[name="yid"]', '#usernamereg-yid',
        'input[aria-label*="user"]', 'input[aria-label*="email"]',
        'input[placeholder*="email"]', 'input[placeholder*="user"]',
    ], timeout=5000)
    if email_sel:
        await focus_blur_field(page, email_sel)
        await _human_fill(page, email_sel, ctx.username)
        await _human_delay(2.0, 4.0)

    await between_steps(page)

    # Password
    pwd_sel = await _wait_for_any(page, [
        '#reg-password', 'input[name="password"]', '#usernamereg-password',
        'input[type="password"]',
        'input[aria-label*="assword"]', 'input[aria-label*="арол"]',
        'input[placeholder*="assword"]',
    ], timeout=5000)
    if pwd_sel:
        await focus_blur_field(page, pwd_sel)
        await _human_fill(page, pwd_sel, ctx.password)
        await _human_delay(1.5, 3.0)

    # Birthday
    await idle_behavior(page, duration_seconds=random.uniform(1.0, 2.0))
    await page.mouse.wheel(0, random.randint(30, 80))
    await _human_delay(0.8, 1.5)

    await between_steps(page)

    month_sel = await _wait_for_any(page, [
        'input[name="mm"]', 'input[placeholder="MM"]',
        'input[placeholder*="Month"]', 'input[aria-label*="onth"]',
        'input[id$="-mm"]', 'input[id*="month"]',
        'input[autocomplete="bday-month"]', '#usernamereg-month',
    ], timeout=5000)
    if month_sel:
        await focus_blur_field(page, month_sel)
        await _human_fill(page, month_sel, str(birthday.month).zfill(2))
        await _human_delay(0.8, 1.5)

    day_sel = await _wait_for_any(page, [
        'input[name="dd"]', 'input[placeholder="DD"]',
        'input[placeholder*="Day"]', 'input[aria-label*="day"]',
        'input[id$="-dd"]', '#usernamereg-day',
    ], timeout=3000)
    if day_sel:
        await focus_blur_field(page, day_sel)
        await _human_fill(page, day_sel, str(birthday.day))
        await _human_delay(0.8, 1.2)

    year_sel = await _wait_for_any(page, [
        'input[name="yyyy"]', 'input[placeholder="YYYY"]',
        'input[placeholder*="Year"]', 'input[aria-label*="ear"]',
        'input[id$="-yyyy"]', '#usernamereg-year',
    ], timeout=3000)
    if year_sel:
        await focus_blur_field(page, year_sel)
        await _human_fill(page, year_sel, str(birthday.year))

    # JS fallback for birthday fields
    if not month_sel or not day_sel or not year_sel:
        ctx._log("Using JS fallback for birthday fields...")
        bday_result = await page.evaluate(f"""() => {{
            const filled = [];
            const allText = document.querySelectorAll('label, span, div, p');
            const fields = [
                {{ label: /month/i, value: '{str(birthday.month).zfill(2)}' }},
                {{ label: /day/i, value: '{str(birthday.day)}' }},
                {{ label: /year/i, value: '{str(birthday.year)}' }},
            ];
            for (const field of fields) {{
                for (const el of allText) {{
                    if (field.label.test(el.textContent) && el.textContent.length < 30) {{
                        const parent = el.closest('fieldset, div, section, form');
                        if (parent) {{
                            const input = parent.querySelector('input:not([type="hidden"]):not([type="checkbox"])');
                            if (input && !input.value) {{
                                input.value = field.value;
                                input.dispatchEvent(new Event('input', {{bubbles: true}}));
                                input.dispatchEvent(new Event('change', {{bubbles: true}}));
                                filled.push(el.textContent.trim().substring(0, 20));
                                break;
                            }}
                        }}
                    }}
                }}
            }}
            return filled;
        }}""")
        if bday_result:
            ctx._log(f"JS fallback filled: {bday_result}")

    # Human reviews filled form before submitting
    await idle_behavior(page, duration_seconds=random.uniform(1.5, 3.0))
    await _human_delay(2.0, 4.0)


async def step_3_submit_form(page, ctx: RegContext, captcha_provider, vision=None):
    """Step 3: Submit form with terms checkbox and email-taken retry."""
    await page.mouse.wheel(0, random.randint(100, 200))
    await _human_delay(0.8, 1.5)

    # Terms checkbox
    terms_checkbox = await _wait_for_any(page, [
        'input[type="checkbox"]',
        'label:has-text("I agree") input',
        '#reg-terms', '#terms',
    ], timeout=3000)
    if terms_checkbox:
        try:
            is_checked = await page.locator(terms_checkbox).first.is_checked()
            if not is_checked:
                ctx._log("Checking 'I agree to terms' checkbox...")
                await _human_click(page, terms_checkbox)
                await _human_delay(0.8, 1.5)
        except Exception:
            try:
                label = await _wait_for_any(page, [
                    'label:has-text("I agree")',
                    'label:has-text("agree to these terms")',
                ], timeout=2000)
                if label:
                    await _human_click(page, label)
                    await _human_delay(0.5, 1.0)
            except Exception:
                pass

    # Review form before submitting (human re-reads filled fields)
    ctx._log("Reviewing form before submit...")
    try:
        await form_review_scan(page)
    except Exception:
        pass
    await reading_dwell(page, min_seconds=2, max_seconds=4)

    # Submit
    ctx._log("Submitting form (Next)...")
    submit_btn = await _wait_for_any(page, [
        'button[name="signup"]', 'button:has-text("Next")',
        'button[type="submit"]', '#reg-submit-button',
        'button:has-text("Continue")', 'button:has-text("Продолжить")',
        'button:has-text("Weiter")', 'button:has-text("Continuer")',
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

    # Vision post-submit check
    if vision:
        try:
            stage = await vision.analyze(page)
            ctx._log(f"[Vision] After submit: {stage['stage']} ({stage['confidence']:.0%})")
            err = await vision.is_error(page)
            if err and err['type'] == 'blocked':
                raise BannedIPError("E305", f"Vision: IP blocked: {err['text']}")
        except (BannedIPError, RateLimitError, FatalError):
            raise
        except Exception:
            pass

    # Email-taken retry
    for email_retry in range(3):
        try:
            page_text = await page.locator('body').inner_text()
            email_taken_phrases = ["email not available", "not available", "already taken", "unavailable"]
            email_taken = any(p.lower() in page_text.lower() for p in email_taken_phrases)
        except Exception:
            email_taken = False

        if email_taken:
            old_username = ctx.username
            ctx.username = generate_username(ctx.first_name, ctx.last_name)
            ctx._log(f"[WARN] Email '{old_username}@yahoo.com' taken! Trying: {ctx.username}")
            email_sel_retry = await _wait_for_any(page, [
                'input[name="yid"]', '#usernamereg-yid', 'input[name="userId"]',
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
        raise RecoverableError("E103", "Yahoo rejected 3 usernames in a row")

    # Post-submit error check
    error = await _check_error_page(page, "after submit")
    if error:
        ctx._err(f"[ERR] Yahoo error after submit: {error}")
        try:
            cookies = await page.context.cookies()
            ipqsd = [c for c in cookies if c.get('name') == 'ipqsd']
            if ipqsd:
                ctx._log(f"[ipqsd] IP Quality Score cookie: {ipqsd[0].get('value', '?')}")
        except Exception:
            pass
        raise BannedIPError("E306", f"Yahoo error after submit: {error[:100]}")

    # CAPTCHA after submit
    await _detect_and_solve_recaptcha(page, captcha_provider, ctx._log)
    await _detect_and_solve_funcaptcha(page, captcha_provider, ctx._log)
    await _human_delay(1, 2)


async def step_4_sms_verification(page, ctx: RegContext, sms_provider, proxy,
                                   captcha_provider, BIRTH_CANCEL_EVENT):
    """Step 4: Full SMS verification — detects Yahoo's country, orders SMS, phone retry loop."""
    # Human reads the phone verification instructions before acting
    await reading_dwell(page, min_seconds=3, max_seconds=6)
    await idle_behavior(page, duration_seconds=random.uniform(1.5, 3.0))

    phone_page_input = await _wait_for_any(page, [
        'input#reg-phone', 'input[name="phone"]', 'input#phone-number',
        'input[placeholder*="hone"]', 'input[aria-label*="hone"]',
        'input[data-type="phone"]', 'input[autocomplete="tel"]',
    ], timeout=15000)

    if not phone_page_input:
        # Fallback: password/terms issues
        ctx._log("[WARN] Phone page not found — checking for terms/checkbox page...")
        await _debug_screenshot(page, "4_yahoo_no_phone_page")
        current_url = page.url or ""
        ctx._log(f"Current URL: {current_url}")

        if "/account/create" in current_url and "/error" not in current_url:
            try:
                page_text = await page.locator('body').inner_text()
                if 'must contain at least 8' in page_text.lower() or 'weak' in page_text.lower():
                    ctx._log("[FIX] Password rejected — re-entering stronger password...")
                    pwd_retry = await _wait_for_any(page, [
                        'input[type="password"]', 'input[name="password"]',
                    ], timeout=3000)
                    if pwd_retry:
                        await page.locator(pwd_retry).first.fill("")
                        await _human_delay(0.3, 0.5)
                        ctx.password = generate_password(16)
                        await _human_fill(page, pwd_retry, ctx.password)
                        await _human_delay(1.5, 2.5)
            except Exception:
                pass

            terms_cb = await _wait_for_any(page, [
                'input[type="checkbox"]', 'label:has-text("I agree") input',
            ], timeout=3000)
            if terms_cb:
                try:
                    is_checked = await page.locator(terms_cb).first.is_checked()
                    if not is_checked:
                        ctx._log("[FIX] Checking terms checkbox...")
                        await _human_click(page, terms_cb)
                        await _human_delay(0.8, 1.5)
                except Exception:
                    try:
                        label = await _wait_for_any(page, ['label:has-text("I agree")'], timeout=2000)
                        if label:
                            await _human_click(page, label)
                            await _human_delay(0.5, 1.0)
                    except Exception:
                        pass

            ctx._log("Re-submitting form after fixes...")
            resubmit = await _wait_for_any(page, [
                'button[name="signup"]', 'button:has-text("Next")',
                'button[type="submit"]', 'button:has-text("Continue")',
            ], timeout=5000)
            if resubmit:
                await _human_click(page, resubmit)
            else:
                await page.keyboard.press("Enter")
            await _human_delay(5, 10)

            phone_page_input = await _wait_for_any(page, [
                'input#reg-phone', 'input[name="phone"]', 'input#phone-number',
                'input[placeholder*="hone"]', 'input[aria-label*="hone"]',
                'input[data-type="phone"]', 'input[autocomplete="tel"]',
            ], timeout=15000)

            if phone_page_input:
                ctx._log("Phone page appeared after re-submit!")
            else:
                raise RecoverableError("E104", "Phone page not found after form re-submit")
        else:
            raise RecoverableError("E105", "Registration not completed - no phone page")

    ctx._log("Detected 'Add your phone number' page")
    if not sms_provider:
        # Check if ANY SMS provider is configured via chain
        from ._helpers import get_sms_chain
        if not get_sms_chain():
            raise FatalError("E502", "Yahoo requires SMS but no SMS provider configured (add 5SIM/Grizzly/SimSMS in Settings)")

    # Detect Yahoo's displayed country code
    yahoo_detected_prefix = None
    yahoo_country_for_sms = None
    try:
        yahoo_detected_prefix = await page.evaluate("""() => {
            const inputs = document.querySelectorAll('input');
            for (const inp of inputs) {
                const val = inp.value.trim();
                if (val.startsWith('+') && val.length <= 5 && val.length >= 2) {
                    return val.replace('+', '');
                }
            }
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
        if yahoo_detected_prefix:
            yahoo_detected_prefix = str(yahoo_detected_prefix).strip()
            yahoo_country_for_sms = PREFIX_TO_SMS_COUNTRY.get(yahoo_detected_prefix)
            ctx._log(f"Yahoo shows: +{yahoo_detected_prefix} → SMS country: {yahoo_country_for_sms or 'unknown'}")
    except Exception:
        pass

    # Order SMS for Yahoo's displayed country
    proxy_geo = getattr(proxy, 'geo', None) if proxy else None
    preferred_geo = yahoo_country_for_sms or proxy_geo
    order = None
    active_sms_provider = None
    expanded_countries = []

    if yahoo_country_for_sms:
        ctx._log(f"[SMS] Must get number for Yahoo's country: {yahoo_country_for_sms} (+{yahoo_detected_prefix})")
        sms_chain = get_sms_chain()
        for provider_name, provider in sms_chain:
            ctx._log(f"[SMS] Trying {provider_name} for {yahoo_country_for_sms}...")
            try:
                result = await asyncio.to_thread(provider.order_number, "yahoo", yahoo_country_for_sms)
                if result and "error" not in result:
                    order = result
                    active_sms_provider = provider
                    expanded_countries = [yahoo_country_for_sms]
                    ctx._log(f"[OK] {provider_name}: got {yahoo_country_for_sms} number: {result.get('number', '?')}")
                    break
                else:
                    err = result.get("error", "?") if result else "no response"
                    ctx._log(f"[SMS] {provider_name}: no {yahoo_country_for_sms} numbers ({err})")
            except Exception as e:
                ctx._log(f"[SMS] {provider_name} error: {e}")

    if not order:
        if yahoo_country_for_sms:
            ctx._log(f"[WARN] No numbers for {yahoo_country_for_sms} on any provider. Trying other countries...")
        ctx._log(f"Ordering number for Yahoo SMS (preferred country: {preferred_geo})...")
        order, active_sms_provider, expanded_countries = await order_sms_with_chain(
            service="yahoo", sms_provider=sms_provider, proxy_geo=preferred_geo,
            page=page, scrape_dropdown=True, _log=ctx._log, _err=ctx._err,
        )

    if not order:
        raise RecoverableError("E106", "No SMS numbers available")

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

    # Strip prefix
    phone_prefix = PHONE_COUNTRY_MAP.get(sms_country)
    local_number = phone_number.lstrip("+")
    if phone_prefix and local_number.startswith(phone_prefix):
        local_number = local_number[len(phone_prefix):]
        ctx._log(f"Stripped prefix +{phone_prefix}, entering: {local_number}")
    else:
        ctx._log(f"Entering as-is: {local_number}")

    # Validate local number length
    if len(local_number) > 12 or len(local_number) < 6:
        ctx._log(f"[WARN] Number {local_number} has {len(local_number)} digits - invalid!")
        try:
            await asyncio.to_thread(sms_provider.cancel_number, order_id)
        except Exception:
            pass
        order, sms_provider_new, expanded_countries = await order_sms_with_chain(
            service="yahoo", sms_provider=sms_provider, proxy_geo=preferred_geo,
            page=page, scrape_dropdown=False, _log=ctx._log, _err=ctx._err,
        )
        if not order:
            raise RecoverableError("E107", "All SMS providers returned invalid-length numbers")
        sms_provider = sms_provider_new
        phone_number = order["number"]
        order_id = order["id"]
        sms_country = order.get("country", "")
        phone_prefix = PHONE_COUNTRY_MAP.get(sms_country)
        local_number = phone_number.lstrip("+")
        if phone_prefix and local_number.startswith(phone_prefix):
            local_number = local_number[len(phone_prefix):]
        ctx._log(f"Re-ordered number: {local_number}")
        ctx._active_sms = {"provider": sms_provider, "order_id": order_id, "number": phone_number}

    # Country code change logic
    yahoo_page_prefix = None
    try:
        yahoo_page_prefix = await page.evaluate("""() => {
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
        if yahoo_page_prefix:
            yahoo_page_prefix = str(yahoo_page_prefix).strip()
    except Exception:
        pass

    sms_prefix = phone_prefix or ""
    country_needs_change = yahoo_page_prefix and sms_prefix and yahoo_page_prefix != sms_prefix
    country_changed = not country_needs_change

    if country_needs_change:
        ctx._log(f"Yahoo shows +{yahoo_page_prefix}, SMS number +{sms_prefix} - need to change")
        try:
            select_el = page.locator('select[name="shortCountryCode"], select[id^="countryCode"]').first
            if await select_el.is_visible(timeout=3000):
                target_iso = COUNTRY_TO_ISO2.get(sms_country, sms_country).upper()
                ctx._log(f"Selecting country in dropdown: {target_iso} (+{sms_prefix})")
                await select_el.select_option(value=target_iso)
                await _human_delay(0.5, 1.0)
                new_val = await select_el.input_value()
                if new_val == target_iso:
                    country_changed = True
                    ctx._log(f"[OK] Country code changed via select: {target_iso}")
                else:
                    try:
                        await select_el.select_option(label=f"(+{sms_prefix})")
                        await _human_delay(0.3, 0.5)
                        country_changed = True
                        ctx._log(f"[OK] Country code changed via label match: +{sms_prefix}")
                    except Exception:
                        ctx._log("[WARN] Label match also failed")
        except Exception as e:
            ctx._log(f"[WARN] select_option failed: {e}")

        if not country_changed:
            try:
                all_inputs = await page.locator('input').all()
                for inp in all_inputs:
                    val = (await inp.input_value()).strip()
                    if val.startswith('+') and 2 <= len(val) <= 5:
                        await inp.fill(f"+{sms_prefix}")
                        await _human_delay(0.3, 0.5)
                        new_val = (await inp.input_value()).strip()
                        if new_val == f"+{sms_prefix}":
                            country_changed = True
                            ctx._log(f"[OK] Country code changed via .fill(): +{sms_prefix}")
                        break
            except Exception:
                pass

        if not country_changed:
            page_country = PREFIX_TO_SMS_COUNTRY.get(yahoo_page_prefix)
            if page_country:
                ctx._log(f"[WARN] Can't change +{yahoo_page_prefix}→+{sms_prefix}. Re-ordering for {page_country}...")
                try:
                    await asyncio.to_thread(sms_provider.cancel_number, order_id)
                except Exception:
                    pass
                try:
                    new_order = await asyncio.to_thread(sms_provider.order_number, "yahoo", page_country)
                    if new_order and "error" not in new_order:
                        phone_number = new_order["number"]
                        order_id = new_order["id"]
                        sms_country = new_order.get("country", page_country)
                        phone_prefix = PHONE_COUNTRY_MAP.get(sms_country)
                        local_number = phone_number.lstrip("+")
                        if phone_prefix and local_number.startswith(phone_prefix):
                            local_number = local_number[len(phone_prefix):]
                        ctx._log(f"[OK] New number for +{yahoo_page_prefix}: {local_number}")
                        ctx._active_sms = {"provider": sms_provider, "order_id": order_id, "number": phone_number}
                    else:
                        ctx._log(f"[WARN] No {page_country} numbers - entering full number as-is")
                        local_number = f"{sms_prefix}{local_number}"
                except Exception:
                    local_number = f"{sms_prefix}{local_number}"
            else:
                ctx._log(f"[WARN] Unknown prefix +{yahoo_page_prefix} - entering full number")
                local_number = f"{sms_prefix}{local_number}"

    # Fill phone field
    await random_mouse_move(page, steps=3)
    await _human_delay(3.0, 5.0)
    await page.mouse.wheel(0, random.randint(30, 80))
    await _human_delay(0.8, 1.5)
    try:
        await page.locator(phone_page_input).first.fill("")
        await _human_delay(0.3, 0.5)
    except Exception:
        pass
    await _human_fill(page, phone_page_input, local_number)
    ctx._log(f"Entered number: {local_number}")
    await _human_delay(1.5, 3.0)

    # Click "Get code by text" — NEVER WhatsApp
    # Multi-locale: Yahoo shows this page in user's proxy language
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
        'button:has-text("code par texto")',
        # Spanish
        'button:has-text("Enviar código")', 'button:has-text("código por SMS")',
        'button:has-text("mensaje de texto")',
        # Portuguese
        'button:has-text("por SMS")', 'button:has-text("Enviar código por SMS")',
        # Italian
        'button:has-text("via SMS")', 'button:has-text("Ricevi codice")',
        # Turkish
        'button:has-text("SMS ile")', 'button:has-text("SMS gönder")',
        # Dutch
        'button:has-text("per sms")', 'button:has-text("Ontvang code")',
        # Russian
        'button:has-text("Получить код по SMS")', 'button:has-text("Отправить код")',
        # Japanese
        'button:has-text("SMSで")',
        # Korean
        'button:has-text("문자로")',
    ]
    get_code_btn = await _wait_for_any(page, sms_button_texts, timeout=5000)
    if not get_code_btn:
        sms_link_selectors = [
            'a:has-text("Receive code by text")', 'a:has-text("code by text")',
            'a:has-text("Text me")', 'a:has-text("Code per SMS")',
            'a:has-text("SMS erhalten")', 'a:has-text("par SMS")',
            'a:has-text("por SMS")', 'a:has-text("via SMS")',
            'a:has-text("SMS ile")', 'a:has-text("per sms")',
        ]
        sms_link = await _wait_for_any(page, sms_link_selectors, timeout=3000)
        if sms_link:
            get_code_btn = sms_link
            ctx._log("[OK] Found SMS as link")
    if not get_code_btn:
        # Fallback 2: universal SMS keyword on ANY clickable element (button, a, div, span)
        ctx._log("[WARN] SMS button/link not found by locale — trying universal 'SMS' keyword...")
        universal_sms = await _wait_for_any(page, [
            'button:has-text("SMS")', 'a:has-text("SMS")',
            '[role="button"]:has-text("SMS")', 'div:has-text("SMS") >> button',
        ], timeout=3000)
        if universal_sms:
            get_code_btn = universal_sms
            ctx._log("[OK] Found clickable element with 'SMS' text")

    if not get_code_btn:
        # Fallback 3: primary/submit button (SMS is ALWAYS the primary action, WhatsApp is secondary)
        ctx._log("[WARN] No SMS element found — using primary button (SMS is always primary)...")
        primary_btn = await _wait_for_any(page, [
            'button[type="submit"]',
            'button.primary', 'button[class*="primary"]', 'button[class*="Primary"]',
            '#send-code-button', 'button[data-type="sms"]',
            'button[class*="btn-primary"]', 'button[class*="cta"]',
        ], timeout=3000)
        if primary_btn:
            get_code_btn = primary_btn
            ctx._log("[OK] Using primary/submit button")

    if not get_code_btn:
        # Fallback 4: first visible button on page (excluding WhatsApp text)
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
        # Absolute last resort: just press Enter
        ctx._log("[WARN] No button found at all — pressing Enter as last resort")
        await page.keyboard.press("Enter")
        await _human_delay(4, 7)

    if not get_code_btn:
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
                    "not a valid phone", "invalid phone", "try another number",
                    "provide another one", "unable to verify this number",
                    "not supported", "invalid number",
                ]
                is_rejected = any(p.lower() in page_text.lower() for p in rejection_phrases)
            except Exception:
                is_rejected = False

            if not is_rejected:
                curr = page.url
                if 'challenge/fail' in curr or '/error' in curr:
                    captcha_on_fail = await _detect_and_solve_recaptcha(page, captcha_provider, ctx._log)
                    if captcha_on_fail:
                        await _human_delay(3, 5)
                        curr2 = page.url
                        if 'challenge/fail' not in curr2 and '/error' not in curr2:
                            phone_accepted = True
                            break
                    try:
                        await asyncio.to_thread(sms_provider.cancel_number, order_id)
                    except Exception:
                        pass
                    raise BannedIPError("E307", f"Yahoo blocked: challenge/fail ({curr})")

                try:
                    phone_still_visible = await page.locator(phone_page_input).first.is_visible()
                except Exception:
                    phone_still_visible = False
                if phone_still_visible:
                    is_rejected = True
                else:
                    phone_accepted = True
                    break

            # Phone rejected — get new number
            ctx._log(f"Yahoo rejected number {display_phone} - getting new one")
            await _debug_screenshot(page, f"yahoo_phone_rejected_{phone_attempt}")
            try:
                await asyncio.to_thread(sms_provider.cancel_number, order_id)
            except Exception:
                pass

            new_order, new_provider, new_provider_name = await get_next_sms_number(
                service="yahoo", current_provider=sms_provider,
                current_provider_name=_current_sms_provider_name or 'simsms',
                expanded_countries=expanded_countries, _log=ctx._log, _err=ctx._err,
            )
            if new_provider:
                sms_provider = new_provider
                _current_sms_provider_name = new_provider_name
            if not new_order:
                raise RecoverableError("E108", "SMS error getting new number")

            phone_number = new_order["number"]
            order_id = new_order["id"]
            new_sms_country = new_order.get("country", sms_country)
            display_phone = phone_number if phone_number.startswith("+") else f"+{phone_number}"

            new_phone_prefix = PHONE_COUNTRY_MAP.get(new_sms_country, phone_prefix)
            local_number = phone_number.lstrip("+")
            if new_phone_prefix and local_number.startswith(new_phone_prefix):
                local_number = local_number[len(new_phone_prefix):]

            if new_sms_country != sms_country:
                try:
                    select_el = page.locator('select[name="shortCountryCode"], select[id^="countryCode"]').first
                    if await select_el.is_visible(timeout=2000):
                        target_iso = COUNTRY_TO_ISO2.get(new_sms_country, new_sms_country).upper()
                        await select_el.select_option(value=target_iso)
                        await _human_delay(0.5, 1.0)
                except Exception:
                    pass
            sms_country = new_sms_country
            phone_prefix = new_phone_prefix

            try:
                await page.locator(phone_page_input).first.fill("")
            except Exception:
                pass
            await _human_fill(page, phone_page_input, local_number)
            ctx._log(f"Entered new number: {local_number}")
            await _human_delay(1.5, 3.0)

            get_code_btn = await _wait_for_any(page, [
                'button:has-text("Get code by text")', 'button:has-text("code by text")',
                'button:has-text("Text me")', 'button:has-text("Send code")',
                'button[type="submit"]', '#send-code-button',
            ], timeout=5000)
            if not get_code_btn:
                await page.keyboard.press("Enter")
                await _human_delay(2, 4)

        if not phone_accepted:
            raise RecoverableError("E109", f"Yahoo rejected {max_phone_retries} numbers in a row")

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

        ctx._log("Waiting for Yahoo SMS code...")

        sms_url = page.url
        if 'challenge/fail' in sms_url or '/error' in sms_url:
            captcha_solved = await _detect_and_solve_recaptcha(page, captcha_provider, ctx._log)
            if not captcha_solved:
                try:
                    await asyncio.to_thread(sms_provider.cancel_number, order_id)
                except Exception:
                    pass
                raise BannedIPError("E308", f"Yahoo challenge/fail after phone: {sms_url}")
            await _human_delay(3, 5)

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
            ctx._log("[WARN] SMS code field NOT FOUND")
            await _debug_screenshot(page, "yahoo_no_sms_field")

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
            try:
                await page.locator(f'input#verify-code-{i}').first.fill(digit)
                await _human_delay(0.1, 0.3)
            except Exception:
                if first_digit:
                    await page.locator(first_digit).first.fill(code_digits)
                break
        await _human_delay(0.5, 1)

        verify_btn = await _wait_for_any(page, [
            'button[name="validate"]', 'button:has-text("Verify")',
            'button:has-text("Next")', 'button[type="submit"]',
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

    ctx._display_phone = display_phone


async def step_5_verify_success(page, ctx: RegContext) -> bool:
    """Step 5: Verify registration succeeded."""
    ctx.email = f"{ctx.username}@yahoo.com"
    final_url = page.url
    ctx._log(f"Final URL: {final_url}")

    registration_success = False
    try:
        success_indicators_url = [
            "mail.yahoo.com", "account/create/success",
            "login.yahoo.com/account/verify", "login.yahoo.com/account/challenge",
            "/welcome", "/myaccount", "/manage_account",
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
        ctx._log(f"Success check: error ({e})")
        on_create = "/account/create" in final_url
        on_success = "/account/create/success" in final_url
        if not on_create or on_success:
            registration_success = True

    if not registration_success:
        ctx._err(f"[FAIL] Registration NOT confirmed! URL: {final_url}")
        await _debug_screenshot(page, "yahoo_registration_not_confirmed")
        raise FatalError("E504", f"Registration not confirmed: {final_url}")

    return True


# ── Main Orchestrator ────────────────────────────────────────────────────────────


async def register_single_yahoo(
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
    """Register a single Yahoo account using the Defensive Coding Template."""
    if ACTIVE_PAGES is None:
        ACTIVE_PAGES = {}
    if BIRTH_CANCEL_EVENT is None:
        BIRTH_CANCEL_EVENT = threading.Event()
    if not name_pool:
        logger.error("[Yahoo] [FAIL] No names! Load a name pack before registration.")
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

    def _log(msg: str):
        n = getattr(thread_log, '_worker_id', 0) + 1 if thread_log else '?'
        logger.info(f"[Yahoo][Thread {n}] {msg}")
        if thread_log:
            thread_log.current_action = f"Thread {n}: {msg}"
            try: db.commit()
            except Exception: pass

    def _err(msg: str):
        n = getattr(thread_log, '_worker_id', 0) + 1 if thread_log else '?'
        logger.error(f"[Yahoo][Thread {n}] {msg}")
        if thread_log:
            thread_log.error_message = f"Thread {n}: {msg}"[:500]
            try: db.commit()
            except Exception: pass

    _proxy_geo = (proxy.geo or "").upper() if proxy else ""
    ctx = RegContext(
        provider="yahoo",
        username=username,
        password=password,
        email=f"{username}@yahoo.com",
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

    vision = None
    try:
        from ..vision import VisionEngine
        vision = VisionEngine("yahoo", debug=True)
        _log("[Vision] Vision Engine active")
    except Exception as ve:
        logger.debug(f"[Yahoo] Vision not available: {ve}")

    ctx._active_sms = None
    _sms_success = False
    reset_chain_state("yahoo")

    context = await browser_manager.create_context(proxy=proxy, geo=None)

    try:
        page = await context.new_page()
        ACTIVE_PAGES[ctx.thread_id] = {"page": page, "context": context}

        # ── State Machine: steps 0-3 (pre-SMS) ──
        pre_sms_steps = [
            ("warmup",      step_0_warmup,      (ctx,)),
            ("navigate",    step_1_navigate,    (ctx, proxy, db, vision)),
            ("fill_form",   step_2_fill_form,   (ctx, birthday)),
            ("submit_form", step_3_submit_form, (ctx, captcha_provider, vision)),
        ]
        result = await run_flow_machine(page, ctx, pre_sms_steps, BIRTH_CANCEL_EVENT)
        if result is None:
            return None

        # Step 4-5: SMS + verify (complex args, run directly with safe_screenshot)
        try:
            await step_4_sms_verification(page, ctx, sms_provider, proxy,
                                           captcha_provider, BIRTH_CANCEL_EVENT)
        except (RecoverableError, RateLimitError, BannedIPError, CaptchaFailError, FatalError):
            await _safe_screenshot(page, "yahoo_sms_error", _log)
            raise
        except Exception as e:
            await _safe_screenshot(page, "yahoo_sms_crash", _log)
            raise FatalError("E599", f"sms_verification: {str(e)[:200]}")

        try:
            await step_5_verify_success(page, ctx)
        except (RecoverableError, RateLimitError, BannedIPError, CaptchaFailError, FatalError):
            await _safe_screenshot(page, "yahoo_verify_error", _log)
            raise
        except Exception as e:
            await _safe_screenshot(page, "yahoo_verify_crash", _log)
            raise FatalError("E599", f"verify_success: {str(e)[:200]}")

        # ── Save session, fingerprint, and create account ──
        _sms_success = True
        display_phone = getattr(ctx, '_display_phone', '')

        account = Account(
            email=ctx.email, password=ctx.password, provider="yahoo",
            first_name=ctx.first_name, last_name=ctx.last_name,
            gender="random", birthday=birthday,
            geo=proxy.geo if proxy and hasattr(proxy, 'geo') else None,
            language=ctx.language or 'en',
            birth_ip=f"{proxy.host}" if proxy else None, status="new",
        )
        db.add(account)
        db.commit()
        db.refresh(account)

        # Save session (cookies/localStorage) with real account ID
        try:
            account.browser_profile_path = await browser_manager.save_session(context, account.id)
            db.commit()
        except Exception as se:
            logger.warning(f"[Yahoo] Session save warning: {se}")

        # Save fingerprint for profile persistence
        try:
            fp_data = getattr(context, '_leomail_fingerprint', None)
            if fp_data:
                browser_manager.save_fingerprint(account.id, fp_data)
                account.user_agent = fp_data.get("user_agent", "")
                db.commit()
                logger.info(f"[Yahoo] Fingerprint saved for account {account.id}")
        except Exception as fp_err:
            logger.warning(f"[Yahoo] Fingerprint save warning: {fp_err}")

        logger.info(f"[OK] Yahoo registered: {ctx.email}")
        export_account_to_file(account, {"sms_phone": display_phone})

        try:
            from ...services.imap_checker import verify_account_imap
            await verify_account_imap(account, db, _log, _err)
        except Exception as imap_e:
            logger.debug(f"[Yahoo] IMAP check skipped: {imap_e}")

        try:
            from ..human_behavior import post_registration_warmup
            _log("[OK] Post-reg session warmup...")
            await post_registration_warmup(page, provider="yahoo")
        except Exception as warmup_e:
            logger.debug(f"[Yahoo] Post-reg warmup error: {warmup_e}")

        return account

    except (RateLimitError, BannedIPError, CaptchaFailError, FatalError, RecoverableError):
        raise
    except Exception as e:
        logger.error(f"[FAIL] Yahoo registration failed: {e}", exc_info=True)
        _err(str(e)[:500])
        raise FatalError("E599", f"Unhandled: {str(e)[:200]}")
    finally:
        if ctx._active_sms and not _sms_success:
            try:
                await asyncio.to_thread(ctx._active_sms["provider"].cancel_order, ctx._active_sms["order_id"])
                logger.info(f"[Yahoo] [WARN] SMS cancelled (crash recovery): {ctx._active_sms['number']}")
            except Exception:
                pass
        ACTIVE_PAGES.pop(ctx.thread_id, None)
        try:
            await context.close()
        except Exception:
            pass
