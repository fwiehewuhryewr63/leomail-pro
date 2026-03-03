"""
Leomail v4 - Outlook/Hotmail Registration Engine (Defensive Coding Template)
Registers outlook.com / hotmail.com accounts via signup.live.com.
Flow: signup -> email/username -> password -> birthday (country+month+day+year) -> name -> FunCaptcha -> prompts -> done
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
    detect_and_solve_funcaptcha as _detect_and_solve_funcaptcha,
    debug_screenshot as _debug_screenshot,
    scan_for_block_signals as _scan_for_block_signals,
    clean_session as _clean_session,
    rate_limiter as _rate_limiter,
    RateLimitError, BannedIPError, FatalError, RecoverableError, CaptchaFailError,
    RegContext, verify_page_state, block_check, run_step,
    export_account_to_file,
)


# Shared selectors
_NEXT_SELECTORS = ['#iSignupAction', 'input[type="submit"]', 'button[type="submit"]']


# ── Step Functions ───────────────────────────────────────────────────────────────


async def step_0_warmup(page, ctx: RegContext):
    """Step 0: Quick warmup — single Google visit to establish session."""
    ctx._log("Quick session warmup...")
    try:
        await page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=15000)
        await _human_delay(1, 2)
        await random_mouse_move(page, steps=2)
    except Exception as warmup_e:
        logger.debug(f"Warmup error (proxy may be dead): {warmup_e}")

    warmup_url = page.url or ""
    if "chrome-error" in warmup_url or "about:blank" == warmup_url:
        ctx._log("[WARN] Proxy not working, warmup failed")


async def step_1_navigate(page, ctx: RegContext, proxy, db):
    """Step 1: Navigate to signup.live.com. Checks: dead proxy, block signals."""
    ctx._log("Opening registration page...")
    try:
        await page.goto(
            "https://signup.live.com/signup",
            wait_until="domcontentloaded",
            timeout=60000,
        )
    except Exception as nav_e:
        logger.warning(f"[Outlook] Navigation error: {nav_e}")

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
                logger.warning(f"Proxy marked DEAD during birth: {proxy.host}:{proxy.port}")
            except Exception:
                pass
        raise FatalError("E501", f"Proxy dead: {current_url}")

    # Check for error/block pages
    if "error" in current_url.split("?")[0].lower() or "blocked" in current_url.lower():
        ctx._err(f"[ERR] MS returned error page (URL: {current_url})")
        raise BannedIPError("E301", f"MS error page: {current_url}")

    # Block scan
    await block_check(page, ctx.provider, ctx, "navigate")

    await random_mouse_move(page, steps=3)
    ctx._log(f"Page: {page.url}")


async def step_2_email_mode(page, ctx: RegContext):
    """Step 2: Handle 'Get a new email address' link and detect domain dropdown."""
    new_email_link = page.locator(
        'a#liveSwitch, a[id*="Switch"], a:has-text("new email"), '
        'a:has-text("новый"), a:has-text("Get a new")'
    )
    ctx._got_new_email_mode = False
    try:
        if await new_email_link.count() > 0:
            ctx._log("Clicking 'Get a new email'...")
            await new_email_link.first.click()
            await _human_delay(1.5, 3)
            ctx._got_new_email_mode = True
    except Exception:
        pass

    if ctx._got_new_email_mode:
        domain_dropdown = await _wait_for_any(page, [
            'select#LiveDomainBoxList', '#LiveDomainBoxList',
            'select[name="DomainList"]',
        ], timeout=3000)
        if domain_dropdown:
            ctx._log("Username-only mode (domain dropdown visible)")
        else:
            ctx._got_new_email_mode = False
            ctx._log("Domain dropdown not visible, using full email")


async def step_3_enter_email(page, ctx: RegContext, domain: str):
    """Step 3: Enter email/username with retry on taken username (up to 3 times)."""
    await block_check(page, ctx.provider, ctx, "enter_email")

    email_selectors = [
        'input[name="MemberName"]', '#MemberName', '#iMemberName',
        'input[name="Email"]',
        'input[type="email"]', 'input[type="text"][name="MemberName"]',
        'input[aria-label*="email"]', 'input[aria-label*="Email"]',
        'input[placeholder*="email"]', 'input[placeholder*="Email"]',
        'input[id*="floatingLabel"]',
    ]
    ctx._log(f"Entering email: {ctx.email}")
    found = await _wait_and_find(page, email_selectors, "email", ctx.username, ctx._log, ctx._err, timeout=20000)
    if not found:
        raise RecoverableError("E101", "Email field not found")

    got_new_email_mode = getattr(ctx, '_got_new_email_mode', False)
    text_to_enter = ctx.username if got_new_email_mode else ctx.email
    ctx._log(f"Entering: {text_to_enter}")

    await _human_fill(page, found, text_to_enter)
    await _human_delay(0.8, 1.5)

    # Select domain if needed
    if got_new_email_mode and domain != "outlook.com":
        domain_sel = await _wait_for_any(page, [
            'select#LiveDomainBoxList', '#LiveDomainBoxList',
            'select[name="DomainList"]', 'select[aria-label*="domain"]',
        ], timeout=5000)
        if domain_sel:
            ctx._log(f"Selecting domain: @{domain}")
            await page.locator(domain_sel).first.select_option(domain)
            await _human_delay(0.5, 1)

    # Click Next
    next_btn = await _wait_for_any(page, _NEXT_SELECTORS, timeout=5000)
    if next_btn:
        await _human_click(page, next_btn)
    else:
        await page.keyboard.press("Enter")
    await _human_delay(3, 6)

    # Email-taken retry (up to 3)
    for email_retry in range(3):
        err_text = await _check_error_on_page(page)
        if err_text:
            old_username = ctx.username
            ctx.username = generate_username(ctx.first_name, ctx.last_name)
            ctx.email = f"{ctx.username}@{domain}"
            ctx._log(f"[WARN] Email '{old_username}@{domain}' taken: {err_text}. Trying: {ctx.email}")
            text_to_enter = ctx.username if got_new_email_mode else ctx.email
            found2 = await _wait_for_any(page, email_selectors, timeout=5000)
            if found2:
                await page.locator(found2).first.fill("")
                await _human_fill(page, found2, text_to_enter)
            await _human_delay(0.5, 1)
            next_retry = await _wait_for_any(page, _NEXT_SELECTORS, timeout=3000)
            if next_retry:
                await _human_click(page, next_retry)
            else:
                await page.keyboard.press("Enter")
            await _human_delay(3, 5)
        else:
            break
    else:
        raise RecoverableError("E102", "MS rejected 3 emails in a row")


async def step_4_password(page, ctx: RegContext):
    """Step 4: Enter password and click Next."""
    await block_check(page, ctx.provider, ctx, "password")

    ctx._log("Entering password...")
    pwd_selectors = [
        'input[name="Password"]', '#PasswordInput', 'input[type="password"]',
        '#iPasswordInput', 'input[name="passwd"]', '#Password',
        'input[aria-label*="assword"]', 'input[aria-label*="арол"]',
        'input[data-purpose*="assword"]', 'input[placeholder*="assword"]',
        'input[placeholder*="арол"]',
    ]
    found = await _wait_and_find(page, pwd_selectors, "password", ctx.username, ctx._log, ctx._err, timeout=25000)
    if not found:
        raise RecoverableError("E103", "Password field not found")

    await _human_fill(page, found, ctx.password)
    await _human_delay(0.5, 1.2)

    next_btn = await _wait_for_any(page, _NEXT_SELECTORS, timeout=3000)
    if next_btn:
        await _human_click(page, next_btn)
    else:
        await page.keyboard.press("Enter")
    await _human_delay(2, 4)


async def step_5_birthday(page, ctx: RegContext, birthday, proxy):
    """Step 5: Enter birthday (country + month + day + year) using Fluent UI comboboxes."""
    ctx._log("Entering date of birth...")
    await _human_delay(1, 2)
    await _step_screenshot(page, "before_birthday", ctx.username)

    month_names = [
        "", "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]
    month_name = month_names[birthday.month] if 1 <= birthday.month <= 12 else str(birthday.month)

    # Country selection
    from ...services.geo_resolver import build_geo_profile, resolve_proxy_geo
    proxy_geo = resolve_proxy_geo(proxy) if proxy else None
    geo_profile = build_geo_profile(proxy_geo) if proxy_geo else None

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
    ctx._log(f"Selecting country: {chosen_country} (GEO: {proxy_geo or 'auto'})")

    country_ok = await _fluent_combobox_select(page, [
        '#countryDropdownId',
        'button[name="countryDropdownName"]',
        'button[aria-label*="ountry"]',
        'button[aria-label*="тран"]',
        'button[role="combobox"]:first-of-type',
    ], chosen_country, "Country", ctx._log, timeout=5000)
    if not country_ok:
        old_country = await _wait_for_any(page, [
            'select[id*="Country"]', 'select[name*="Country"]',
        ], timeout=2000)
        if old_country:
            try:
                await page.locator(old_country).first.select_option("US")
                ctx._log("Country: selected via native select")
            except Exception:
                pass
    await _human_delay(0.5, 1.0)

    # Month
    month_ok = await _fluent_combobox_select(page, [
        '#BirthMonthDropdown',
        'button[name="BirthMonth"]',
        'button[aria-label*="irth month"]',
        'button[aria-label*="есяц"]',
    ], month_name, "Month", ctx._log, timeout=10000)
    if not month_ok:
        old_month = await _wait_for_any(page, [
            '#BirthMonth', 'select[name="BirthMonth"]',
        ], timeout=2000)
        if old_month:
            try:
                await page.locator(old_month).first.select_option(str(birthday.month))
                ctx._log(f"Month: native select ({birthday.month})")
                month_ok = True
            except Exception:
                pass
    if not month_ok:
        ctx._err(f"Failed to select month. URL: {page.url}")
        raise RecoverableError("E104", f"Month field not found at {page.url}")
    await _human_delay(0.3, 0.8)

    # Day
    day_ok = await _fluent_combobox_select(page, [
        '#BirthDayDropdown',
        'button[name="BirthDay"]',
        'button[aria-label*="irth day"]',
        'button[aria-label*="ень рожд"]',
    ], str(birthday.day), "Day", ctx._log, timeout=5000)
    if not day_ok:
        old_day = await _wait_for_any(page, [
            '#BirthDay', 'select[name="BirthDay"]',
        ], timeout=2000)
        if old_day:
            try:
                await page.locator(old_day).first.select_option(str(birthday.day))
                ctx._log(f"Day: native select ({birthday.day})")
            except Exception:
                pass
    await _human_delay(0.3, 0.8)

    # Year
    year_sel = await _wait_for_any(page, [
        'input[name="BirthYear"]', '#BirthYear',
        'input[aria-label*="irth year"]', 'input[aria-label*="од рожд"]',
        'input[type="number"]',
    ], timeout=5000)
    if year_sel:
        await _human_fill(page, year_sel, str(birthday.year))
        ctx._log(f"Year: {birthday.year}")
    else:
        ctx._log("[WARN] Year field not found")
    await _human_delay(0.5, 1)

    # Scroll + submit
    await page.mouse.wheel(0, random.randint(50, 150))
    await _human_delay(0.8, 1.5)

    next_btn = await _wait_for_any(page, _NEXT_SELECTORS, timeout=3000)
    if next_btn:
        await _human_click(page, next_btn)
    else:
        await page.keyboard.press("Enter")
    await _human_delay(2, 4)


async def step_6_name(page, ctx: RegContext):
    """Step 6: Enter first + last name. May not appear on all MS flows."""
    ctx._log(f"Entering name: {ctx.first_name} {ctx.last_name}")
    fn_selectors = [
        '#firstNameInput',
        'input[name="FirstName"]', '#FirstName', '#iFirstName',
        'input[name="DisplayName"]', '#DisplayName',
        'input[placeholder*="имя"]', 'input[placeholder*="irst"]',
        'input[aria-label*="irst name"]', 'input[aria-label*="имя"]',
    ]
    name_found = await _wait_for_any(page, fn_selectors, timeout=8000)
    if name_found:
        ctx._log("Detected name page")
        await _human_fill(page, name_found, ctx.first_name)
        await _human_delay(0.8, 1.5)

        ln_selectors = [
            '#lastNameInput',
            'input[name="LastName"]', '#LastName', '#iLastName',
            'input[placeholder*="фамил"]', 'input[placeholder*="ast"]',
            'input[aria-label*="ast name"]', 'input[aria-label*="фам"]',
        ]
        found_ln = await _wait_for_any(page, ln_selectors, timeout=5000)
        if found_ln:
            await _human_fill(page, found_ln, ctx.last_name)
        await _human_delay(0.5, 1)

        await random_mouse_move(page, steps=2)
        await _human_delay(1.0, 2.0)

        next_btn = await _wait_for_any(page, _NEXT_SELECTORS, timeout=3000)
        if next_btn:
            await _human_click(page, next_btn)
        else:
            await page.keyboard.press("Enter")
        await _human_delay(3, 6)
    else:
        ctx._log("[WARN] Name page not found - possibly already on CAPTCHA")


async def step_7_captcha(page, ctx: RegContext, captcha_provider):
    """Step 7: Handle FunCaptcha or reCAPTCHA. MS serves FunCaptcha primarily."""
    ctx._log("Checking CAPTCHA...")
    captcha_frame = page.locator(
        'iframe[title*="captcha"], iframe[title*="Verification"], '
        'iframe[title*="Human"], iframe[src*="funcaptcha"], '
        'iframe[src*="hsprotect"], #enforcementFrame'
    )
    await _human_delay(2, 4)

    if await captcha_frame.count() > 0:
        captcha_chain = get_captcha_chain()
        if captcha_chain.providers:
            ctx._log("[CAPTCHA] FunCaptcha detected! Solving via CaptchaChain...")
            try:
                # Extract site key
                site_key = "B7D8911C-5CC8-A9A3-35B0-554ACEE604DA"  # MS default
                surl = "https://client-api.arkoselabs.com"
                try:
                    extracted_key = await page.evaluate("""(() => {
                        const frames = document.querySelectorAll('iframe[src*="funcaptcha"], iframe[src*="arkoselabs"]');
                        for (const f of frames) {
                            const m = f.src.match(/pk=([A-F0-9-]+)/i);
                            if (m) return m[1];
                        }
                        const el = document.querySelector('[data-pkey], [data-public-key]');
                        if (el) return el.getAttribute('data-pkey') || el.getAttribute('data-public-key');
                        if (window.enforcement && window.enforcement.publicKey) return window.enforcement.publicKey;
                        return null;
                    })()""")
                    if extracted_key:
                        site_key = extracted_key
                        ctx._log(f"Extracted FunCaptcha key: {site_key[:20]}...")
                except Exception:
                    ctx._log("Using default MS FunCaptcha key")

                # Solve via chain
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
                    ctx._log("[OK] FunCaptcha solved! Injecting token...")
                    await page.evaluate(f"""(() => {{
                        const token = "{token}";
                        try {{
                            var ef = document.getElementById("enforcementFrame");
                            if (ef && ef.contentWindow) {{
                                ef.contentWindow.postMessage(JSON.stringify({{token: token}}), "*");
                            }}
                        }} catch(e) {{}}
                        try {{
                            document.querySelectorAll('input[name*="fc-token"], input[name*="verification"], input[name*="FC"]')
                                .forEach(i => {{ i.value = token; i.dispatchEvent(new Event('change', {{bubbles: true}})); }});
                        }} catch(e) {{}}
                        try {{ if (window.funcaptchaCallback) window.funcaptchaCallback(token); }} catch(e) {{}}
                        try {{ if (window.ArkoseEnforcement) window.ArkoseEnforcement.setConfig({{onCompleted: token}}); }} catch(e) {{}}
                        try {{
                            var evt = new CustomEvent('arkose-completed', {{detail: {{token: token}}}});
                            document.dispatchEvent(evt);
                        }} catch(e) {{}}
                    }})()""")
                    await _human_delay(3, 6)
                    ctx._log("Token injected, waiting...")

                    post_captcha_btn = await _wait_for_any(page, _NEXT_SELECTORS, timeout=5000)
                    if post_captcha_btn:
                        await _human_click(page, post_captcha_btn)
                        await _human_delay(3, 6)
                else:
                    raise CaptchaFailError("E401", "FunCaptcha: all providers failed to solve")
            except CaptchaFailError:
                raise
            except asyncio.TimeoutError:
                raise CaptchaFailError("E402", "FunCaptcha solve timeout (180s)")
            except Exception as e:
                ctx._err(f"CAPTCHA error: {str(e)[:200]}")
                raise CaptchaFailError("E403", f"FunCaptcha error: {str(e)[:200]}")
        else:
            raise CaptchaFailError("E404", "FunCaptcha required but no CAPTCHA providers configured")
    else:
        # No FunCaptcha — check for reCAPTCHA fallback
        ctx._log("No FunCaptcha iframe — checking for reCAPTCHA fallback...")
        recaptcha_solved = await _detect_and_solve_recaptcha(page, captcha_provider, ctx._log)
        if recaptcha_solved:
            ctx._log("[OK] reCAPTCHA solved (MS fallback)")
            await _human_delay(3, 6)
            post_captcha_btn = await _wait_for_any(page, _NEXT_SELECTORS, timeout=5000)
            if post_captcha_btn:
                await _human_click(page, post_captcha_btn)
                await _human_delay(3, 6)
        else:
            ctx._log("No CAPTCHA detected - continuing")

    # Post-check: block signals after CAPTCHA
    await block_check(page, ctx.provider, ctx, "post_captcha")


async def step_8_post_prompts(page, ctx: RegContext):
    """Step 8: Handle post-captcha prompts (Stay signed in?, promo pages)."""
    await _human_delay(2, 4)

    # "Stay signed in?"
    stay_signed_in = await _wait_for_any(page, [
        '#KmsiBanner', '#acceptButton', 'button:has-text("Yes")',
        'input[value="Yes"]', '#idSIButton9',
    ], timeout=5000)
    if stay_signed_in:
        ctx._log("Clicking 'Yes' on 'Stay signed in?'")
        await _human_click(page, stay_signed_in)
        await _human_delay(3, 5)

    # Promo pages
    skip_promo = await _wait_for_any(page, [
        'button:has-text("Skip")', 'a:has-text("Skip")',
        'button:has-text("Пропустить")', 'a:has-text("Пропустить")',
        'button:has-text("No thanks")', 'a:has-text("No thanks")',
        'button:has-text("Maybe later")', '#declineButton',
    ], timeout=3000)
    if skip_promo:
        ctx._log("Skipping promo page...")
        await _human_click(page, skip_promo)
        await _human_delay(2, 4)


async def step_9_verify_success(page, ctx: RegContext) -> bool:
    """Step 9: Verify registration succeeded."""
    ctx._log("Checking result...")
    await _human_delay(2, 4)
    final_url = page.url.lower()
    ctx._log(f"Final URL: {final_url}")

    registration_success = False
    try:
        success_indicators = [
            "outlook.live.com", "signup.live.com/signup?sru",
            "/MailSetup", "account.microsoft.com",
            "outlook.office.com", "outlook.office365.com",
        ]
        if any(ind in final_url for ind in success_indicators):
            registration_success = True
            ctx._log("[OK] URL confirms successful registration")
        elif "signup.live.com" not in final_url:
            registration_success = True
            ctx._log("[OK] Left registration page")
        else:
            page_text = await page.locator('body').inner_text()
            fail_indicators = ["something went wrong", "couldn't create", "error", "blocked"]
            if any(fi.lower() in page_text.lower() for fi in fail_indicators):
                ctx._err("[FAIL] Page contains error indicators")
                await _debug_screenshot(page, "outlook_error_on_page")
            else:
                ctx._log("[WARN] Still on signup.live.com, but no errors")
                await _debug_screenshot(page, "outlook_still_on_signup")
    except Exception as e:
        ctx._log(f"Success check: error ({e}), counting as success if URL changed")
        if "signup.live.com" not in final_url:
            registration_success = True

    if not registration_success:
        ctx._err(f"[FAIL] Registration NOT confirmed! URL: {final_url}")
        await _debug_screenshot(page, "outlook_not_confirmed")
        raise FatalError("E502", f"Registration not confirmed: {final_url}")

    return True


# ── Main Orchestrator ────────────────────────────────────────────────────────────


async def register_single_outlook(
    browser_manager: BrowserManager,
    proxy: Proxy | None,
    name_pool: list,
    captcha_provider: CaptchaProvider | None,
    db: Session,
    thread_log: ThreadLog | None = None,
    domain: str = "outlook.com",
    ACTIVE_PAGES: dict = None,
    BIRTH_CANCEL_EVENT: threading.Event = None,
) -> Account | None:
    """Register a single Outlook/Hotmail account using the Defensive Coding Template."""
    if ACTIVE_PAGES is None:
        ACTIVE_PAGES = {}
    if BIRTH_CANCEL_EVENT is None:
        BIRTH_CANCEL_EVENT = threading.Event()
    if not name_pool:
        logger.error("[Outlook] [FAIL] No names! Load a name pack before registration.")
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
    email = f"{username}@{domain}"
    provider_name = "hotmail" if "hotmail" in domain else "outlook"

    # ── Create RegContext ──
    def _log(msg: str):
        n = getattr(thread_log, '_worker_id', 0) + 1 if thread_log else '?'
        logger.info(f"[Outlook][Thread {n}] {msg}")
        if thread_log:
            thread_log.current_action = f"Thread {n}: {msg}"
            try: db.commit()
            except Exception: pass

    def _err(msg: str):
        n = getattr(thread_log, '_worker_id', 0) + 1 if thread_log else '?'
        logger.error(f"[Outlook][Thread {n}] {msg}")
        if thread_log:
            thread_log.error_message = f"Thread {n}: {msg}"[:500]
            try: db.commit()
            except Exception: pass

    ctx = RegContext(
        provider=provider_name,
        username=username,
        password=password,
        email=email,
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
        vision = VisionEngine("outlook", debug=True)
        _log("[Vision] Vision Engine active")
    except Exception as ve:
        logger.debug(f"[Outlook] Vision not available: {ve}")

    context = await browser_manager.create_context(proxy=proxy, geo=None)

    try:
        page = await context.new_page()
        ACTIVE_PAGES[ctx.thread_id] = {"page": page, "context": context}

        # ── Execute Steps ──
        await step_0_warmup(page, ctx)

        await step_1_navigate(page, ctx, proxy, db)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        await step_2_email_mode(page, ctx)

        await step_3_enter_email(page, ctx, domain)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        await step_4_password(page, ctx)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        await step_5_birthday(page, ctx, birthday, proxy)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        await step_6_name(page, ctx)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        await step_7_captcha(page, ctx, captcha_provider)

        await step_8_post_prompts(page, ctx)

        await step_9_verify_success(page, ctx)

        # ── Save session and create account ──
        try:
            session_path = await browser_manager.save_session(context, 0)
        except Exception as se:
            logger.warning(f"[Outlook] Session save warning: {se}")
            session_path = None

        account = Account(
            email=ctx.email,
            password=ctx.password,
            provider=provider_name,
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

        logger.info(f"[OK] Outlook registered: {ctx.email}")
        export_account_to_file(account)

        # IMAP verification (non-blocking)
        try:
            from ...services.imap_checker import verify_account_imap
            await verify_account_imap(account, db, _log, _err)
        except Exception as imap_e:
            logger.debug(f"[Outlook] IMAP check skipped: {imap_e}")

        # Post-registration warmup
        try:
            from ..human_behavior import post_registration_warmup
            _log("[OK] Post-reg session warmup...")
            await post_registration_warmup(page, provider=provider_name)
        except Exception as warmup_e:
            logger.debug(f"[Outlook] Post-reg warmup error: {warmup_e}")

        return account

    except (RateLimitError, BannedIPError, CaptchaFailError, FatalError, RecoverableError):
        raise
    except Exception as e:
        logger.error(f"[FAIL] Outlook registration failed: {e}", exc_info=True)
        _err(str(e)[:500])
        raise FatalError("E599", f"Unhandled: {str(e)[:200]}")
    finally:
        ACTIVE_PAGES.pop(ctx.thread_id, None)
        try:
            await context.close()
        except Exception:
            pass
