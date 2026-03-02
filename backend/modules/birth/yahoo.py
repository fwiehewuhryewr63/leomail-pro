"""
Leomail v3 - Yahoo Registration Engine (with Vision CV)
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
    order_sms_with_chain, order_sms_retry, get_next_sms_number,
    reset_chain_state, SMS_CODE_TIMEOUT,
    export_account_to_file,
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

    context = await browser_manager.create_context(
        proxy=proxy,
        device_type="desktop",
        geo=None,
    )

    def _log(msg: str):
        n = getattr(thread_log, '_worker_id', 0) + 1 if thread_log else '?'
        logger.info(f"[Yahoo][Thread {n}] {msg}")
        if thread_log:
            thread_log.current_action = f"Thread {n}: {msg}"
            try:
                db.commit()
            except Exception:
                pass

    def _err(msg: str):
        n = getattr(thread_log, '_worker_id', 0) + 1 if thread_log else '?'
        logger.error(f"[Yahoo][Thread {n}] {msg}")
        if thread_log:
            thread_log.error_message = f"Thread {n}: {msg}"[:500]
            try:
                db.commit()
            except Exception:
                pass

    # ── Initialize Vision Engine (OCR + stage detection) ──
    vision = None
    try:
        from ..vision import VisionEngine
        vision = VisionEngine("yahoo", debug=True)
        _log("[Vision] Vision Engine active - OCR + stage detection")
    except Exception as ve:
        logger.debug(f"[Yahoo] Vision not available: {ve}")

    # ── Fast error page detector (saves 20s vs waiting for fields) ──
    async def _check_error_page(page, context_msg=""):
        """Quick 2s check for Yahoo error/block pages. Returns error string or None."""
        url = page.url or ""
        # URL-based detection
        error_urls = ["/error", "challenge/fail", "challenge/recaptcha", "/blocked",
                      "guce.yahoo", "consent.yahoo", "/sorry"]
        for pattern in error_urls:
            if pattern in url.lower():
                return f"Error URL detected: {url}"
        # DOM-based detection (fast - querySelector is instant)
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

    _active_sms = None  # Track SMS order for crash recovery (cancel if unused)
    _sms_success = False  # Set True when SMS code verified
    _current_sms_provider_name = None  # Track provider name for chain rotation

    # Reset SMS chain state for this registration attempt
    reset_chain_state("yahoo")

    try:
        page = await context.new_page()
        thread_id = thread_log.id if thread_log else 0
        ACTIVE_PAGES[thread_id] = {"page": page, "context": context}

        # Fast warmup - just a quick Google visit (2-3s instead of 15-30s)
        _log("Quick session warmup...")
        try:
            await page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=15000)
            await _human_delay(1, 2)
            await random_mouse_move(page, steps=2)
        except Exception:
            pass

        # Step 1: Navigate to Yahoo signup
        _log("Opening Yahoo registration page...")
        try:
            await page.goto(
                "https://login.yahoo.com/account/create",
                wait_until="domcontentloaded",
                timeout=60000,
            )
        except Exception as nav_e:
            logger.warning(f"[Yahoo] Navigation error: {nav_e}")

        await _human_delay(2, 4)

        # CRITICAL: Check if proxy is dead
        current_url = page.url or ""
        if "chrome-error" in current_url or "about:blank" == current_url:
            _err(f"[ERR] Proxy DEAD - page failed to load (URL: {current_url})")
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
            _err(f"[ERR] Yahoo returned error page - IP blocked or rate limited (URL: {current_url})")
            return None

        await random_mouse_move(page, steps=3)
        _log(f"Page: {page.url}")

        # ── Vision: detect initial stage ──
        if vision:
            try:
                stage = await vision.analyze(page)
                _log(f"[Vision] Stage: {stage['stage']} ({stage['confidence']:.0%}) - {stage['description']}")
                err = await vision.is_error(page)
                if err:
                    _err(f"[Vision] Error detected: {err['type']} - {err['text']}")
                    return None
            except Exception as ve:
                logger.debug(f"[Yahoo] Vision stage detect: {ve}")

        # Yahoo: all fields on one page - fill with human-like behavior
        _log(f"Entering data: {first_name} {last_name} / {username}")

        # ── FAST ERROR CHECK (2s vs 20s timeout) ──
        error = await _check_error_page(page, "before firstname")
        if error:
            _err(f"[ERR] Yahoo error before form: {error}")
            return None

        # First name
        fn_sel = await _wait_and_find(page, [
            '#reg-firstName', 'input[name="firstName"]', '#usernamereg-firstName',
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
            '#reg-lastName', 'input[name="lastName"]', '#usernamereg-lastName',
            'input[aria-label*="ast"]', 'input[aria-label*="фам"]',
            'input[placeholder*="Last"]', 'input[placeholder*="фам"]',
            'input[autocomplete="family-name"]',
        ], timeout=5000)
        if ln_sel:
            await _human_fill(page, ln_sel, last_name)
            await _human_delay(1.2, 2.8)

        # Small scroll down - humans do this
        await page.mouse.wheel(0, random.randint(50, 150))
        await _human_delay(0.5, 1.0)

        # Email / Username
        email_sel = await _wait_for_any(page, [
            '#reg-userId', 'input[name="userId"]',
            'input[name="yid"]', '#usernamereg-yid',
            'input[aria-label*="user"]', 'input[aria-label*="email"]',
            'input[placeholder*="email"]', 'input[placeholder*="user"]',
        ], timeout=5000)
        if email_sel:
            await _human_fill(page, email_sel, username)
            await _human_delay(1.5, 3.0)  # Human thinks about username

        # Password
        pwd_sel = await _wait_for_any(page, [
            '#reg-password', 'input[name="password"]', '#usernamereg-password',
            'input[type="password"]',
            'input[aria-label*="assword"]', 'input[aria-label*="арол"]',
            'input[placeholder*="assword"]',
        ], timeout=5000)
        if pwd_sel:
            await _human_fill(page, pwd_sel, password)
            await _human_delay(1.0, 2.0)

        # Birthday - scroll down a bit first
        await page.mouse.wheel(0, random.randint(30, 80))
        await _human_delay(0.5, 1.0)

        # Yahoo birthday: input[type="tel"] fields, NOT selects
        month_sel = await _wait_for_any(page, [
            'input[name="mm"]', 'input[placeholder="MM"]',
            'input[placeholder*="Month"]', 'input[placeholder*="onth"]',
            'input[aria-label="Birthday month"]', 'input[aria-label*="onth"]',
            'input[id$="-mm"]',
        ], timeout=5000)
        if month_sel:
            await _human_fill(page, month_sel, str(birthday.month).zfill(2))
            await _human_delay(0.5, 1.2)

        day_sel = await _wait_for_any(page, [
            'input[name="dd"]', 'input[placeholder="DD"]',
            'input[placeholder*="Day"]', 'input[placeholder*="ay"]',
            'input[aria-label="Birthday day"]', 'input[aria-label*="day"]',
            'input[id$="-dd"]',
        ], timeout=3000)
        if day_sel:
            await _human_fill(page, day_sel, str(birthday.day))
            await _human_delay(0.5, 1.0)

        year_sel = await _wait_for_any(page, [
            'input[name="yyyy"]', 'input[placeholder="YYYY"]',
            'input[placeholder*="Year"]', 'input[placeholder*="ear"]',
            'input[aria-label="Birthday year"]', 'input[aria-label*="ear"]',
            'input[id$="-yyyy"]',
        ], timeout=3000)
        if year_sel:
            await _human_fill(page, year_sel, str(birthday.year))

        await _human_delay(1.5, 3.0)  # Human reviews form before submitting

        # Scroll to Next button (Yahoo no longer has a terms checkbox)
        await page.mouse.wheel(0, random.randint(100, 200))
        await _human_delay(0.8, 1.5)

        # ── Check for 'I agree to these terms' checkbox (Yahoo 2025+ forms) ──
        terms_checkbox = await _wait_for_any(page, [
            'input[type="checkbox"]',
            'label:has-text("I agree") input',
            '#reg-terms', '#terms',
        ], timeout=3000)
        if terms_checkbox:
            try:
                is_checked = await page.locator(terms_checkbox).first.is_checked()
                if not is_checked:
                    _log("Checking 'I agree to terms' checkbox...")
                    await _human_click(page, terms_checkbox)
                    await _human_delay(0.8, 1.5)
            except Exception:
                # Fallback: click the label if checkbox isn't directly clickable
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

        # Click Next / Continue / Submit - with "Email not available" retry
        _log("Submitting form (Next)...")
        submit_btn = await _wait_for_any(page, [
            'button[name="signup"]',
            'button:has-text("Next")', 'button:has-text("Next")',
            'button[type="submit"]', '#reg-submit-button',
            'button:has-text("Continue")', 'button:has-text("Продолжить")',
            '#usernamereg-submitBtn',
        ], timeout=5000)
        if submit_btn:
            try:
                await page.locator(submit_btn).first.wait_for(state="attached", timeout=3000)
                await _human_click(page, submit_btn)
            except Exception:
                _log("Button disabled - trying Enter...")
                await page.keyboard.press("Enter")
        else:
            await page.keyboard.press("Enter")

        await _human_delay(4, 8)  # Longer wait for page transition

        # ── Vision: check post-submit stage ──
        if vision:
            try:
                stage = await vision.analyze(page)
                _log(f"[Vision] After submit: {stage['stage']} ({stage['confidence']:.0%})")
                err = await vision.is_error(page)
                if err and err['type'] == 'blocked':
                    _err(f"[Vision] IP blocked: {err['text']}")
                    return None
            except Exception:
                pass

        # ── CRITICAL: Detect "Email not available" and retry with new username ──
        for email_retry in range(3):
            try:
                page_text = await page.locator('body').inner_text()
                email_taken_phrases = [
                    "email not available",
                    "not available",
                    "already taken",
                    "already taken",
                    "unavailable",
                ]
                email_taken = any(p.lower() in page_text.lower() for p in email_taken_phrases)
            except Exception:
                email_taken = False

            if email_taken:
                old_username = username
                username = generate_username(first_name, last_name)
                _log(f"[WARN] Email '{old_username}@yahoo.com' taken! Trying: {username}")
                # Re-fill username field
                email_sel_retry = await _wait_for_any(page, [
                    'input[name="yid"]', '#usernamereg-yid', 'input[name="userId"]',
                ], timeout=3000)
                if email_sel_retry:
                    await page.locator(email_sel_retry).first.fill("")
                    await _human_fill(page, email_sel_retry, username)
                    await _human_delay(1, 2)
                    # Re-click submit
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
                    _err("Email field not found for re-entry")
                    return None
            else:
                break  # No error - proceed
        else:
            _err(f"Yahoo rejected 3 usernames in a row - try different names")
            return None

        # ── Post-submit: Handle Yahoo's "Add your phone number" page ──
        post_url = page.url
        _log(f"После отправки: {post_url}")

        # ── FAST ERROR CHECK after submit ──
        error = await _check_error_page(page, "after submit")
        if error:
            _err(f"[ERR] Yahoo error after submit: {error}")
            return None

        # Check for reCAPTCHA after submit
        await _detect_and_solve_recaptcha(page, captcha_provider, _log)
        await _human_delay(1, 2)

        # Yahoo shows a separate "Add your phone number" page after registration
        # We need to detect it, ORDER the SMS number, fill phone, and click "Get code by text"
        phone_page_input = await _wait_for_any(page, [
            'input#reg-phone', 'input[name="phone"]', 'input#phone-number',
            'input[placeholder*="hone"]', 'input[aria-label*="hone"]',
            'input[data-type="phone"]', 'input[autocomplete="tel"]',
        ], timeout=15000)

        if phone_page_input:
            _log("Detected 'Add your phone number' page")

            if not sms_provider:
                _err("Yahoo requires SMS but no SMS provider configured")
                return None

            # ── STEP 1: Order SMS via shared auto-intelligence ──
            # Uses proxy geo + page dropdown to pick country, tries all providers
            proxy_geo = getattr(proxy, 'geo', None) if proxy else None
            _log("Ordering number for Yahoo SMS...")

            order, active_sms_provider, expanded_countries = await order_sms_with_chain(
                service="yahoo",
                sms_provider=sms_provider,
                proxy_geo=proxy_geo,
                page=page,
                scrape_dropdown=True,
                _log=_log,
                _err=_err,
            )

            if not order:
                return None

            # Update sms_provider to whichever worked
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
            _active_sms = {"provider": sms_provider, "order_id": order_id, "number": phone_number}
            display_phone = phone_number if phone_number.startswith("+") else f"+{phone_number}"
            _log(f"Number: {display_phone} (country: {sms_country})")

            # ── STEP 3: Strip phone prefix to get local number ──
            phone_prefix = PHONE_COUNTRY_MAP.get(sms_country)
            local_number = phone_number.lstrip("+")
            if phone_prefix and local_number.startswith(phone_prefix):
                local_number = local_number[len(phone_prefix):]
                _log(f"Stripped prefix +{phone_prefix}, entering: {local_number}")
            else:
                _log(f"Entering as-is: {local_number}")

            # ── STEP 4: Change Yahoo's country code IF it doesn't match ──
            # Detect what country Yahoo is currently showing on the page
            yahoo_page_prefix = None
            try:
                yahoo_page_prefix = await page.evaluate("""() => {
                    // Check select elements for current country code
                    const selects = document.querySelectorAll('select[id^="countryCode"], select');
                    for (const sel of selects) {
                        const opt = sel.options[sel.selectedIndex];
                        if (opt) {
                            const m = opt.text.match(/\\+(\\d{1,4})/);
                            if (m) return m[1];
                        }
                    }
                    // Check inputs showing "+XX"
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

            target_iso = COUNTRY_TO_ISO2.get(sms_country, "").upper()
            sms_prefix = phone_prefix or ""
            country_needs_change = yahoo_page_prefix and sms_prefix and yahoo_page_prefix != sms_prefix
            country_changed = not country_needs_change  # Already correct = no change needed

            if country_needs_change:
                _log(f"Yahoo shows +{yahoo_page_prefix}, SMS number +{sms_prefix} - need to change")

                # Method 1: select_option on <select> elements (Yahoo uses <select> for country)
                try:
                    selects = await page.locator('select').all()
                    for sel in selects:
                        try:
                            # Find option matching our prefix
                            changed_via_select = await page.evaluate(f"""(sel) => {{
                                for (const opt of sel.options) {{
                                    if (opt.text.includes('+{sms_prefix}') || opt.value === '{sms_prefix}' || opt.value === '{target_iso}') {{
                                        sel.value = opt.value;
                                        sel.dispatchEvent(new Event('change', {{bubbles: true}}));
                                        return true;
                                    }}
                                }}
                                return false;
                            }}""", sel)
                            if changed_via_select:
                                country_changed = True
                                _log(f"Country code changed via <select>: +{sms_prefix}")
                                break
                        except Exception:
                            continue
                except Exception:
                    pass

                # Method 2: JS setter on input elements
                if not country_changed:
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
                            _log(f"Country code changed via JS input: +{sms_prefix}")
                    except Exception:
                        pass

                if not country_changed:
                    # Country change failed - the page still shows +yahoo_page_prefix
                    # DO NOT enter a number formatted for +sms_prefix into +yahoo_page_prefix field!
                    # Instead: cancel current number and re-order one matching the page's country
                    page_country = PREFIX_TO_SMS_COUNTRY.get(yahoo_page_prefix)
                    if page_country:
                        _log(f"[WARN] Не удалось сменить +{yahoo_page_prefix}->+{sms_prefix}. "
                             f"Canceling number and ordering from {page_country} (countries: +{yahoo_page_prefix})")
                        # Cancel current order
                        try:
                            await asyncio.to_thread(sms_provider.cancel_order, order_id)
                        except Exception:
                            pass
                        # Re-order from page's country
                        new_order = await order_sms_retry(
                            service="yahoo",
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
                            _log(f"[OK] New number for +{yahoo_page_prefix}: {local_number}")
                        else:
                            _err(f"Failed to order number for +{yahoo_page_prefix}")
                            return None
                    else:
                        _log(f"[WARN] Failed to change code, unknown prefix +{yahoo_page_prefix} - entering full number")
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
            _log(f"Entered number: {local_number}")
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
                        _log(f"Attempt #{phone_attempt + 1} with new number...")

                    _log("Pressing 'Get code by text'...")
                    await _human_click(page, get_code_btn)
                    await _human_delay(4, 7)

                    # ── CRITICAL: Yahoo often shows reCAPTCHA AFTER clicking 'Get code' ──
                    # We must detect and solve it BEFORE checking for challenge/fail!
                    for captcha_attempt in range(2):
                        captcha_solved = await _detect_and_solve_recaptcha(page, captcha_provider, _log)
                        if captcha_solved:
                            _log(f"CAPTCHA solved after 'Get code' (attempt {captcha_attempt + 1})")
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
                        # Only check for SPECIFIC phone rejection phrases
                        # Removed generic phrases ("oops", "something went wrong") that cause false positives
                        rejection_phrases = [
                            "don't support this number",
                            "doesn't look right",
                            "not a valid phone",
                            "invalid phone",
                            "try another number",
                            "provide another one",
                            "unable to verify this number",
                            "not supported",
                            "invalid number",
                        ]
                        is_rejected = any(phrase.lower() in page_text.lower() for phrase in rejection_phrases)
                        if is_rejected:
                            # Log which phrase matched for debugging
                            matched = [p for p in rejection_phrases if p.lower() in page_text.lower()]
                            _log(f"Yahoo error on page: {matched}")
                    except Exception:
                        is_rejected = False

                    if not is_rejected:
                        # Also check URL for challenge/fail
                        curr = page.url
                        _log(f"After 'Get code': {curr}")
                        if 'challenge/fail' in curr or '/error' in curr:
                            # One more attempt: maybe there's a captcha on this page too
                            captcha_on_fail = await _detect_and_solve_recaptcha(page, captcha_provider, _log)
                            if captcha_on_fail:
                                _log("CAPTCHA solved on challenge/fail page, trying again...")
                                await _human_delay(3, 5)
                                # Check if we moved away from the fail page
                                curr2 = page.url
                                if 'challenge/fail' not in curr2 and '/error' not in curr2:
                                    phone_accepted = True
                                    break
                            _err("Yahoo blocked: challenge/fail")
                            await _debug_screenshot(page, "yahoo_blocked", _log)
                            try:
                                await asyncio.to_thread(sms_provider.cancel_number, order_id)
                            except Exception:
                                pass
                            return None

                        # Check if we ACTUALLY moved from the phone page
                        # If still on /account/create with phone form visible, phone was NOT accepted
                        try:
                            phone_still_visible = await page.locator(phone_page_input).first.is_visible()
                        except Exception:
                            phone_still_visible = False

                        if phone_still_visible:
                            _log("[WARN] Phone form still visible - number not accepted, trying another")
                            is_rejected = True
                        else:
                            phone_accepted = True
                            break

                    # Phone rejected - cancel old number and get a new one
                    _log(f"Yahoo rejected number {display_phone} - getting new one")
                    await _debug_screenshot(page, f"yahoo_phone_rejected_{phone_attempt}", _log)
                    try:
                        await asyncio.to_thread(sms_provider.cancel_number, order_id)
                    except Exception:
                        pass

                    # Order new number via chain rotation (3 attempts/provider, then next)
                    new_order, new_provider, new_provider_name = await get_next_sms_number(
                        service="yahoo",
                        current_provider=sms_provider,
                        current_provider_name=_current_sms_provider_name or 'simsms',
                        expanded_countries=expanded_countries,
                        _log=_log,
                        _err=_err,
                    )
                    if new_provider:
                        sms_provider = new_provider
                        _current_sms_provider_name = new_provider_name
                    if not new_order:
                        _err("SMS error getting new number")
                        return None

                    phone_number = new_order["number"]
                    order_id = new_order["id"]
                    sms_country = new_order.get("country", sms_country)
                    display_phone = phone_number if phone_number.startswith("+") else f"+{phone_number}"
                    _log(f"New number: {display_phone} (country: {sms_country})")

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
                    _log(f"Entered new number: {local_number}")
                    await _human_delay(1.5, 3.0)

                    # Re-find the button (might change state)
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
                    if not get_code_btn:
                        _log("Кнопка 'Get code' not foundа - пробуем Enter")
                        await page.keyboard.press("Enter")
                        await _human_delay(2, 4)

                if not phone_accepted:
                    _err(f"Yahoo rejected {max_phone_retries} numbers in a row - proxy or SMS service issue")
                    return None
            else:
                _log("[WARN] Get code by text button not found - trying Enter")
                await page.keyboard.press("Enter")
                await _human_delay(4, 7)
        else:
            _log("[WARN] Phone page not found - checking for terms/checkbox page...")
            await _debug_screenshot(page, "4_yahoo_no_phone_page", _log)

            # Yahoo might be showing terms page or password error - check current URL
            current_url = page.url or ""
            _log(f"Current URL: {current_url}")

            # Check if still on /account/create — password may be invalid or terms not checked
            if "/account/create" in current_url and "/error" not in current_url:
                # Try to find and fix password error
                try:
                    page_text = await page.locator('body').inner_text()
                    if 'must contain at least 8' in page_text.lower() or 'weak' in page_text.lower():
                        _log("[FIX] Password rejected — re-entering stronger password...")
                        pwd_retry = await _wait_for_any(page, [
                            'input[type="password"]', 'input[name="password"]',
                        ], timeout=3000)
                        if pwd_retry:
                            await page.locator(pwd_retry).first.fill("")
                            await _human_delay(0.3, 0.5)
                            # Generate a new stronger password
                            password = generate_password(16)
                            await _human_fill(page, pwd_retry, password)
                            await _human_delay(1.5, 2.5)
                except Exception:
                    pass

                # Try terms checkbox again
                terms_cb = await _wait_for_any(page, [
                    'input[type="checkbox"]',
                    'label:has-text("I agree") input',
                ], timeout=3000)
                if terms_cb:
                    try:
                        is_checked = await page.locator(terms_cb).first.is_checked()
                        if not is_checked:
                            _log("[FIX] Checking terms checkbox...")
                            await _human_click(page, terms_cb)
                            await _human_delay(0.8, 1.5)
                    except Exception:
                        try:
                            label = await _wait_for_any(page, [
                                'label:has-text("I agree")',
                            ], timeout=2000)
                            if label:
                                await _human_click(page, label)
                                await _human_delay(0.5, 1.0)
                        except Exception:
                            pass

                # Re-submit the form
                _log("Re-submitting form after fixes...")
                resubmit = await _wait_for_any(page, [
                    'button[name="signup"]', 'button:has-text("Next")',
                    'button[type="submit"]', 'button:has-text("Continue")',
                ], timeout=5000)
                if resubmit:
                    await _human_click(page, resubmit)
                else:
                    await page.keyboard.press("Enter")
                await _human_delay(5, 10)

                # Re-check for phone page
                phone_page_input = await _wait_for_any(page, [
                    'input#reg-phone', 'input[name="phone"]', 'input#phone-number',
                    'input[placeholder*="hone"]', 'input[aria-label*="hone"]',
                    'input[data-type="phone"]', 'input[autocomplete="tel"]',
                ], timeout=15000)

                if phone_page_input:
                    _log("Phone page appeared after re-submit!")
                    # Continue to the phone handling logic below — but we can't
                    # easily restart the block, so we need a different approach.
                    # For now, return None and let retry handle it
                    _err("Registration not completed - retry needed after form fixes")
                    return None

            _err("Registration not completed")
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

            _log("Waiting for Yahoo SMS code...")
            _log(f"Page: {page.url}")

            # Check if Yahoo redirected to challenge/fail BEFORE waiting for code
            sms_url = page.url
            if 'challenge/fail' in sms_url or '/error' in sms_url:
                _err(f"Yahoo redirected to challenge/fail after phone: {sms_url}")
                await _debug_screenshot(page, "yahoo_challenge_after_phone", _log)
                # Try solving captcha on this page
                captcha_solved = await _detect_and_solve_recaptcha(page, captcha_provider, _log)
                if not captcha_solved:
                    try:
                        await asyncio.to_thread(sms_provider.cancel_number, order_id)
                    except Exception:
                        pass
                    return None
                await _human_delay(3, 5)

            # Yahoo uses various code input formats:
            # - 6 individual digit inputs: #verify-code-0 to #verify-code-5
            # - Single code input: input[name="code"]
            # - Other variations
            first_digit = await _wait_for_any(page, [
                'input#verify-code-0', 'input[aria-label="Code 1"]',
                'input[name="code"]', 'input[name="verificationCode"]',
                'input[name="verify_code"]', 'input[type="tel"][maxlength="1"]',
                'input[data-type="code"]', 'input.phone-code',
                'input[autocomplete="one-time-code"]',
            ], timeout=30000)

            if first_digit:
                _log(f"[OK] SMS code field found: {first_digit}")
            else:
                _log("[WARN] SMS code field NOT FOUND - Yahoo did not show verification form!")
                _log(f"Current URL: {page.url}")
                await _debug_screenshot(page, "yahoo_no_sms_field", _log)
                # Log page text for debugging
                try:
                    body_text = await page.locator('body').inner_text()
                    # Take first 300 chars to see what Yahoo shows
                    _log(f"Page text: {body_text[:300]}")
                except Exception:
                    pass

            sms_result = await asyncio.to_thread(sms_provider.get_sms_code, order_id, 300, BIRTH_CANCEL_EVENT)
            sms_code = None
            if isinstance(sms_result, dict):
                sms_code = sms_result.get("code")
                if sms_result.get("error"):
                    _err(f"SMS error: {sms_result['error']}")
                    try:
                        await asyncio.to_thread(sms_provider.cancel_number, order_id)
                    except Exception:
                        pass
                    return None
            elif isinstance(sms_result, str):
                sms_code = sms_result

            if not sms_code:
                _err("SMS code not received")
                try:
                    await asyncio.to_thread(sms_provider.cancel_number, order_id)
                except Exception:
                    pass
                return None

            _log(f"SMS code: {sms_code}")
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
        final_url = page.url
        _log(f"Final URL: {final_url}")

        # ── CRITICAL: Verify registration actually succeeded ──
        # Check URL and page content for success indicators
        registration_success = False
        try:
            # Yahoo redirects to mail.yahoo.com, or shows welcome/setup/success pages
            success_indicators_url = [
                "mail.yahoo.com",
                "account/create/success",   # Confirmed via real browser testing
                "login.yahoo.com/account/verify",
                "login.yahoo.com/account/challenge",
                "/welcome",
                "/myaccount",
                "/manage_account",
            ]
            if any(ind in final_url.lower() for ind in success_indicators_url):
                registration_success = True
                _log("[OK] URL confirms successful registration")

            # Check if we left the /account/create page (but NOT /account/create/success!)
            if not registration_success:
                # Parse: on create page but NOT on success page = still registering
                on_create = "/account/create" in final_url
                on_success = "/account/create/success" in final_url
                if not on_create or on_success:
                    registration_success = True
                    _log("[OK] Left registration page - counting as success")

            # Final check: look for error indicators
            if registration_success:
                page_text = await page.locator('body').inner_text()
                fail_indicators = ["registration failed", "account could not be created", "registration failed"]
                if any(fi.lower() in page_text.lower() for fi in fail_indicators):
                    registration_success = False
                    _err("[FAIL] Page contains registration error indicators")
        except Exception as e:
            _log(f"Success check: error ({e}), counting as success if URL changed")
            on_create = "/account/create" in final_url
            on_success = "/account/create/success" in final_url
            if not on_create or on_success:
                registration_success = True

        if not registration_success:
            _err(f"[FAIL] Registration NOT confirmed! URL: {final_url}")
            await _debug_screenshot(page, "yahoo_registration_not_confirmed", _log)
            return None

        # Save session
        try:
            session_path = await browser_manager.save_session(context, 0)
        except Exception:
            session_path = None

        _sms_success = True  # SMS was used successfully, don't cancel
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

        logger.info(f"[OK] Yahoo registered: {email}")
        export_account_to_file(account, {"sms_phone": locals().get("display_phone", "")})

        # IMAP verification (non-blocking - don't fail the birth if IMAP is down)
        try:
            from ...services.imap_checker import verify_account_imap
            await verify_account_imap(account, db, _log, _err)
        except Exception as imap_e:
            logger.debug(f"[Yahoo] IMAP check skipped: {imap_e}")

        # Post-registration warmup - visit inbox/settings to age the session
        try:
            from ..human_behavior import post_registration_warmup
            _log("[OK] Post-reg session warmup...")
            await post_registration_warmup(page, provider="yahoo")
        except Exception as warmup_e:
            logger.debug(f"[Yahoo] Post-reg warmup error: {warmup_e}")

        return account

    except Exception as e:
        logger.error(f"[FAIL] Yahoo registration failed: {e}", exc_info=True)
        _err(str(e)[:500])
        return None
    finally:
        # Cancel unused SMS order (crash recovery - don't waste money)
        if _active_sms and not _sms_success:
            try:
                _log_fn = _log if '_log' in dir() else logger.info
                await asyncio.to_thread(_active_sms["provider"].cancel_order, _active_sms["order_id"])
                logger.info(f"[Yahoo] [WARN] SMS cancelled (crash recovery): {_active_sms['number']}")
            except Exception:
                pass
        ACTIVE_PAGES.pop(thread_id, None)
        try:
            await context.close()
        except Exception:
            pass
