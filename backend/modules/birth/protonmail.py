"""
Leomail v3 - ProtonMail Registration Engine
Registers proton.me / protonmail.com accounts.
Flow: account.proton.me/signup -> free plan -> username -> password + repeat -> Proton CAPTCHA -> (optional recovery) -> done
Note: Proton replaced hCaptcha with their own "Proton CAPTCHA" (proof-of-work + visual) in Sep 2023.
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
    scan_for_block_signals as _scan_for_block_signals,
    clean_session as _clean_session,
    rate_limiter as _rate_limiter,
    RateLimitError, BannedIPError, FatalError,
    export_account_to_file,
)


async def register_single_protonmail(
    browser_manager: BrowserManager,
    proxy: Proxy | None,
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
        logger.error("[ProtonMail] [FAIL] No names! Load a name pack before registration.")
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
    # ProtonMail username - letters, numbers, dots, dashes, underscores
    username = username.replace("_", ".").lower()
    email = f"{username}@proton.me"

    context = await browser_manager.create_context(
        proxy=proxy,
        geo=None,
    )

    def _log(msg: str):
        n = getattr(thread_log, '_worker_id', 0) + 1 if thread_log else '?'
        logger.info(f"[ProtonMail][Thread {n}] {msg}")
        if thread_log:
            thread_log.current_action = f"Thread {n}: {msg}"
            try:
                db.commit()
            except Exception:
                pass

    def _err(msg: str):
        n = getattr(thread_log, '_worker_id', 0) + 1 if thread_log else '?'
        logger.error(f"[ProtonMail][Thread {n}] {msg}")
        if thread_log:
            thread_log.error_message = f"Thread {n}: {msg}"[:500]
            try:
                db.commit()
            except Exception:
                pass

    thread_id = thread_log.id if thread_log else 0

    try:
        page = await context.new_page()
        ACTIVE_PAGES[thread_id] = {"page": page, "context": context}

        # ── Step 0: Session warmup (build trust before going to signup) ──
        _log("Session warmup...")
        warmup_sites = [
            ("https://www.google.com", 1, 3),
            ("https://proton.me", 2, 4),
        ]
        for site_url, min_t, max_t in random.sample(warmup_sites, len(warmup_sites)):
            try:
                await page.goto(site_url, wait_until="domcontentloaded", timeout=15000)
                await _human_delay(min_t, max_t)
                await random_mouse_move(page, steps=random.randint(2, 3))
            except Exception:
                pass
        _log("Warmup done")

        # ── Step 1: Navigate to signup ──
        _log("Navigating to registration page...")
        await page.goto("https://account.proton.me/signup", wait_until="domcontentloaded", timeout=60000)
        await _human_delay(2.0, 4.0)

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
            raise FatalError("E501", f"Proxy dead: {current_url}")

        # Universal block signal scan
        block_result = await _scan_for_block_signals(page, "protonmail")
        if block_result["detected"]:
            _err(f"[BLOCK] {block_result['reason']}")
            await _debug_screenshot(page, "proton_block_detected", _log)
            if block_result["action"] == "skip_ip":
                raise BannedIPError("E302", block_result["reason"])
            elif block_result["action"] == "backoff":
                raise RateLimitError("E201", block_result["reason"])

        await _debug_screenshot(page, "proton_signup_page", _log)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        # ── Step 2: Select Free plan ──
        _log("Selecting free plan...")
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
                    _log("Free plan selected")
                    break
            except Exception:
                continue
        await _human_delay(2.0, 3.0)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        # Scroll down to reveal the account creation form
        _log("Scrolling to account form...")
        await page.mouse.wheel(0, 800)
        await _human_delay(1.0, 2.0)

        # ── Step 3: Enter username ──
        # NOTE: Proton wraps #username in a custom component that Playwright
        # considers "not visible". Use JS to focus + set value, then dispatch
        # input events so React picks up the change.
        _log(f"Entering username: {username}")
        try:
            await page.wait_for_selector('#username', state='attached', timeout=10000)
            await _human_delay(0.5, 1.0)
            await page.evaluate("""(username) => {
                const el = document.querySelector('#username');
                el.focus();
                el.value = '';
            }""", username)
            await _human_delay(0.3, 0.5)
            # Type character by character for human-like behavior
            await page.locator('#username').press_sequentially(username, delay=random.randint(30, 90))
            _log(f"Username entered: {username}")
        except Exception as e:
            _err(f"Field not found username: {e}")
            await _debug_screenshot(page, "proton_no_username_field", _log)
            return None

        await _human_delay(1.0, 2.0)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        # ── Step 4: Enter password ──
        _log("Entering password...")
        try:
            await page.wait_for_selector('#password', state='attached', timeout=5000)
            await _human_delay(0.3, 0.6)
            await page.evaluate("""() => {
                const el = document.querySelector('#password');
                el.focus();
                el.value = '';
            }""")
            await _human_delay(0.3, 0.5)
            await page.locator('#password').press_sequentially(password, delay=random.randint(30, 90))
            _log("Password entered")
        except Exception as e:
            _err(f"Password field error: {e}")
            return None

        # ── Step 4b: Enter repeat password ──
        _log("Confirming password...")
        try:
            await page.wait_for_selector('#repeat-password', state='attached', timeout=5000)
            await _human_delay(0.3, 0.6)
            await page.evaluate("""() => {
                const el = document.querySelector('#repeat-password');
                if (el) { el.focus(); el.value = ''; }
            }""")
            await _human_delay(0.3, 0.5)
            await page.locator('#repeat-password').press_sequentially(password, delay=random.randint(30, 90))
            _log("Password confirmed")
        except Exception as e:
            _log(f"[WARN] repeat-password field not found: {e} (may not be required)")

        await _human_delay(1.0, 2.0)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        # ── Step 5: Submit form ──
        _log("Clicking submit button...")
        try:
            submit_btn = page.locator('button[type="submit"]').first
            await submit_btn.scroll_into_view_if_needed(timeout=5000)
            await _human_delay(0.5, 1.0)
            await submit_btn.click(force=True, timeout=5000)
            _log("Form submitted")
        except Exception as e:
            _err(f"Submit button error: {e}")
            return None

        await _human_delay(3.0, 5.0)
        await _debug_screenshot(page, "proton_after_submit", _log)

        # Check for block signals after submit
        block_result = await _scan_for_block_signals(page, "protonmail")
        if block_result["detected"]:
            _err(f"[BLOCK] {block_result['reason']}")
            await _debug_screenshot(page, "proton_block_detected", _log)
            return None

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        # ── Step 6: Handle Proton CAPTCHA / hCaptcha ──
        # Proton switched to their own "Proton CAPTCHA" in Sep 2023:
        # - Proof-of-work challenge (runs in WebWorker)
        # - Visual captcha as fallback
        # We also keep hCaptcha detection as a fallback for edge cases.
        _log("Checking for CAPTCHA...")
        captcha_handled = False

        # Method 1: Proton CAPTCHA (current system)
        # Proton CAPTCHA appears as an iframe or inline challenge
        try:
            proton_captcha = page.locator('[data-testid="captcha"], iframe[src*="captcha"], .captcha-container, [class*="Captcha"]')
            if await proton_captcha.count() > 0:
                _log("[CAPTCHA] Proton CAPTCHA detected")
                # Proton CAPTCHA uses proof-of-work — wait for it to auto-solve
                # The browser computes the PoW challenge automatically
                _log("Waiting for Proton CAPTCHA proof-of-work to complete...")
                for wait_attempt in range(30):  # Up to 60 seconds
                    await _human_delay(1.5, 2.5)
                    # Check if captcha disappeared (solved)
                    still_visible = await proton_captcha.count() > 0
                    if not still_visible:
                        _log("[OK] Proton CAPTCHA completed (auto-solved)")
                        captcha_handled = True
                        break
                    # Check if we moved to a new page
                    if "signup" not in page.url.lower():
                        _log("[OK] Left signup page — CAPTCHA likely passed")
                        captcha_handled = True
                        break
                    # Check for visual challenge that needs human interaction
                    visual_challenge = page.locator('[data-testid="captcha-visual"], .captcha-image, canvas[class*="captcha"]')
                    if await visual_challenge.count() > 0:
                        _log("[WARN] Proton visual CAPTCHA — cannot auto-solve")
                        await _debug_screenshot(page, "proton_visual_captcha", _log)
                        # Try clicking if there's a verify/submit button
                        verify_btn = await _wait_for_any(page, [
                            'button:has-text("Verify")', 'button:has-text("Submit")',
                            'button[type="submit"]',
                        ], timeout=3000)
                        if verify_btn:
                            await _human_click(page, verify_btn)
                            await _human_delay(3, 5)
                        break
                if not captcha_handled:
                    _log("[WARN] Proton CAPTCHA still visible after 60s")
                    await _debug_screenshot(page, "proton_captcha_timeout", _log)
        except Exception as e:
            _log(f"Proton CAPTCHA check error: {e}")

        # Method 2: hCaptcha fallback (for older Proton instances or A/B tests)
        if not captcha_handled:
            try:
                hcaptcha_frame = page.frame_locator('iframe[src*="hcaptcha"]')
                checkbox = hcaptcha_frame.locator('#checkbox')
                if await checkbox.is_visible(timeout=3000):
                    _log("hCaptcha detected (legacy/A-B test) — solving via CaptchaChain...")
                    captcha_chain = get_captcha_chain()
                    if captcha_chain.providers:
                        try:
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
                                    await page.evaluate(f"""
                                        (() => {{
                                            const token = "{solution}";
                                            document.querySelectorAll('[name="h-captcha-response"], [name="g-recaptcha-response"]')
                                                .forEach(el => {{ el.value = token; }});
                                            document.querySelectorAll('textarea[name="h-captcha-response"]')
                                                .forEach(el => {{ el.value = token; el.dispatchEvent(new Event('input', {{bubbles: true}})); }});
                                            try {{ if (window.hcaptcha) window.hcaptcha.execute(); }} catch(e) {{}}
                                        }})()
                                    """)
                                    _log("hCaptcha solved via CaptchaChain [OK]")
                                    captcha_handled = True
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
                                    _err("hCaptcha: CaptchaChain failed to solve")
                            else:
                                _err("hCaptcha: not found sitekey")
                        except asyncio.TimeoutError:
                            _err("hCaptcha: timeout 120s")
                        except Exception as ce:
                            _err(f"hCaptcha error: {ce}")
                    else:
                        await checkbox.click()
                        await _human_delay(3.0, 5.0)
                        _log("hCaptcha: clicking checkbox (no providers)")
            except Exception:
                _log("No hCaptcha detected either")

        await _human_delay(2.0, 4.0)

        # ── Step 7: Skip recovery / Complete registration ──
        _log("Skipping recovery...")
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
                    _log("Skipped")
                    break
            except Exception:
                continue

        await _human_delay(3.0, 5.0)

        # ── Step 8: Verify success ──
        _log("Checking result...")
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
                    _err(f"Username '{username}' already taken")
                    return None
            except Exception:
                pass

        if not registration_success:
            _err(f"[FAIL] Registration NOT confirmed! URL: {final_url}")
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

        logger.info(f"[OK] ProtonMail registered: {email}")
        export_account_to_file(account)
        return account

    except Exception as e:
        logger.error(f"[FAIL] ProtonMail registration failed: {e}", exc_info=True)
        _err(str(e)[:500])
        return None
    finally:
        ACTIVE_PAGES.pop(thread_id, None)
        try:
            await context.close()
        except Exception:
            pass
