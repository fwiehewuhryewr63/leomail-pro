"""
Leomail v4 - ProtonMail Registration Engine (Defensive Coding Template)
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
    RateLimitError, BannedIPError, FatalError, RecoverableError, CaptchaFailError,
    RegContext, verify_page_state, block_check, run_step,
    export_account_to_file, get_expected_language,
)


# ── Step Functions ───────────────────────────────────────────────────────────────


async def step_0_warmup(page, ctx: RegContext):
    """Step 0: Session warmup — visit neutral sites to build trust."""
    ctx._log("Session warmup...")
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
    ctx._log("Warmup done")


async def step_1_navigate(page, ctx: RegContext, proxy, db):
    """Step 1: Navigate to signup. Checks: dead proxy, block signals."""
    ctx._log("Navigating to registration page...")
    await page.goto(
        "https://account.proton.me/signup",
        wait_until="domcontentloaded",
        timeout=60000,
    )
    await _human_delay(2.0, 4.0)

    # Pre-check: proxy alive?
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

    # Block scan
    await block_check(page, ctx.provider, ctx, "navigate")

    await _debug_screenshot(page, "proton_signup_page")
    ctx._log(f"Page loaded: {page.url}")


async def step_2_select_plan(page, ctx: RegContext):
    """Step 2: Select Free plan. Handles: plan page may already be skipped."""
    ctx._log("Selecting free plan...")

    # Pre-check: are we on a page with plan selection?
    free_plan_selectors = [
        'button:has-text("Get Proton Free")',
        'button:has-text("Free")',
        '[data-testid="select-free"]',
        'a[href*="free"]',
    ]
    plan_clicked = False
    for sel in free_plan_selectors:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=3000):
                await btn.click()
                ctx._log("Free plan selected")
                plan_clicked = True
                break
        except Exception:
            continue

    if not plan_clicked:
        ctx._log("[SKIP] No plan selection page — already on signup form")

    await _human_delay(2.0, 3.0)

    # Scroll to reveal form
    ctx._log("Scrolling to account form...")
    await page.mouse.wheel(0, 800)
    await _human_delay(1.0, 2.0)


async def step_3_username(page, ctx: RegContext):
    """Step 3: Enter username. Handles: Proton custom input component."""
    # Block scan before typing
    await block_check(page, ctx.provider, ctx, "username")

    ctx._log(f"Entering username: {ctx.username}")
    try:
        await page.wait_for_selector('#username', state='attached', timeout=10000)
        await _human_delay(0.5, 1.0)
        # Proton wraps #username in custom component — JS focus + clear first
        await page.evaluate("""(username) => {
            const el = document.querySelector('#username');
            el.focus();
            el.value = '';
        }""", ctx.username)
        await _human_delay(0.3, 0.5)
        await page.locator('#username').press_sequentially(
            ctx.username, delay=random.randint(30, 90)
        )
        ctx._log(f"Username entered: {ctx.username}")
    except Exception as e:
        ctx._err(f"Field not found username: {e}")
        await _debug_screenshot(page, "proton_no_username_field")
        raise RecoverableError("E101", f"Username field not found: {e}")

    await _human_delay(1.0, 2.0)


async def step_4_password(page, ctx: RegContext):
    """Step 4: Enter password + repeat password. Handles: repeat-password may be absent."""
    # Block scan
    await block_check(page, ctx.provider, ctx, "password")

    # Password
    ctx._log("Entering password...")
    try:
        await page.wait_for_selector('#password', state='attached', timeout=5000)
        await _human_delay(0.3, 0.6)
        await page.evaluate("""() => {
            const el = document.querySelector('#password');
            el.focus();
            el.value = '';
        }""")
        await _human_delay(0.3, 0.5)
        await page.locator('#password').press_sequentially(
            ctx.password, delay=random.randint(30, 90)
        )
        ctx._log("Password entered")
    except Exception as e:
        ctx._err(f"Password field error: {e}")
        raise RecoverableError("E103", f"Password field not found: {e}")

    # Repeat password (may not exist on all Proton variants)
    ctx._log("Confirming password...")
    try:
        await page.wait_for_selector('#repeat-password', state='attached', timeout=5000)
        await _human_delay(0.3, 0.6)
        await page.evaluate("""() => {
            const el = document.querySelector('#repeat-password');
            if (el) { el.focus(); el.value = ''; }
        }""")
        await _human_delay(0.3, 0.5)
        await page.locator('#repeat-password').press_sequentially(
            ctx.password, delay=random.randint(30, 90)
        )
        ctx._log("Password confirmed")
    except Exception as e:
        ctx._log(f"[WARN] repeat-password field not found: {e} (may not be required)")

    await _human_delay(1.0, 2.0)


async def step_5_submit(page, ctx: RegContext):
    """Step 5: Submit form. Post-check: block signals after submit."""
    ctx._log("Clicking submit button...")
    try:
        submit_btn = page.locator('button[type="submit"]').first
        await submit_btn.scroll_into_view_if_needed(timeout=5000)
        await _human_delay(0.5, 1.0)
        await submit_btn.click(force=True, timeout=5000)
        ctx._log("Form submitted")
    except Exception as e:
        ctx._err(f"Submit button error: {e}")
        raise RecoverableError("E104", f"Submit button not found: {e}")

    await _human_delay(3.0, 5.0)
    await _debug_screenshot(page, "proton_after_submit")

    # Post-check: block signals after submit
    await block_check(page, ctx.provider, ctx, "post_submit")


async def step_6_captcha(page, ctx: RegContext):
    """Step 6: Handle Proton CAPTCHA (PoW + visual) or hCaptcha fallback."""
    ctx._log("Checking for CAPTCHA...")
    captcha_handled = False

    # Method 1: Proton CAPTCHA (current system — proof of work)
    try:
        proton_captcha = page.locator(
            '[data-testid="captcha"], iframe[src*="captcha"], '
            '.captcha-container, [class*="Captcha"]'
        )
        if await proton_captcha.count() > 0:
            ctx._log("[CAPTCHA] Proton CAPTCHA detected — waiting for PoW auto-solve...")
            for wait_attempt in range(30):  # Up to 60 seconds
                await _human_delay(1.5, 2.5)
                still_visible = await proton_captcha.count() > 0
                if not still_visible:
                    ctx._log("[OK] Proton CAPTCHA completed (auto-solved)")
                    captcha_handled = True
                    break
                if "signup" not in page.url.lower():
                    ctx._log("[OK] Left signup page — CAPTCHA likely passed")
                    captcha_handled = True
                    break
                # Visual challenge fallback
                visual = page.locator(
                    '[data-testid="captcha-visual"], .captcha-image, canvas[class*="captcha"]'
                )
                if await visual.count() > 0:
                    ctx._log("[WARN] Proton visual CAPTCHA — cannot auto-solve")
                    await _debug_screenshot(page, "proton_visual_captcha")
                    verify_btn = await _wait_for_any(page, [
                        'button:has-text("Verify")', 'button:has-text("Submit")',
                        'button[type="submit"]',
                    ], timeout=3000)
                    if verify_btn:
                        await _human_click(page, verify_btn)
                        await _human_delay(3, 5)
                    raise CaptchaFailError("E401", "Proton visual CAPTCHA not solvable")
            if not captcha_handled:
                ctx._log("[WARN] Proton CAPTCHA still visible after 60s")
                await _debug_screenshot(page, "proton_captcha_timeout")
                raise CaptchaFailError("E402", "Proton CAPTCHA timeout (60s)")
    except CaptchaFailError:
        raise
    except Exception as e:
        ctx._log(f"Proton CAPTCHA check error: {e}")

    # Method 2: hCaptcha fallback (legacy A/B test)
    if not captcha_handled:
        try:
            hcaptcha_frame = page.frame_locator('iframe[src*="hcaptcha"]')
            checkbox = hcaptcha_frame.locator('#checkbox')
            if await checkbox.is_visible(timeout=3000):
                ctx._log("hCaptcha detected (legacy/A-B test) — solving via CaptchaChain...")
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
                            ctx._log(f"hCaptcha sitekey: {site_key[:20]}...")
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
                                ctx._log("hCaptcha solved via CaptchaChain [OK]")
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
                                raise CaptchaFailError("E403", "hCaptcha: solver returned no solution")
                        else:
                            raise CaptchaFailError("E404", "hCaptcha: sitekey not found")
                    except CaptchaFailError:
                        raise
                    except asyncio.TimeoutError:
                        raise CaptchaFailError("E405", "hCaptcha: solver timeout 120s")
                    except Exception as ce:
                        ctx._err(f"hCaptcha error: {ce}")
                else:
                    await checkbox.click()
                    await _human_delay(3.0, 5.0)
                    ctx._log("hCaptcha: clicking checkbox (no providers)")
        except CaptchaFailError:
            raise
        except Exception:
            ctx._log("No hCaptcha detected either")

    await _human_delay(2.0, 4.0)


async def step_7_skip_recovery(page, ctx: RegContext):
    """Step 7: Skip recovery email/phone prompts."""
    ctx._log("Skipping recovery...")
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
                ctx._log("Skipped")
                break
        except Exception:
            continue
    await _human_delay(3.0, 5.0)


async def step_8_verify_success(page, ctx: RegContext) -> bool:
    """Step 8: Verify registration succeeded. Returns True if account created."""
    ctx._log("Checking result...")
    await _debug_screenshot(page, "proton_result")

    final_url = page.url
    registration_success = False

    # Check URL indicators
    success_indicators = ["mail", "inbox", "welcome", "congratulations", "setup"]
    for indicator in success_indicators:
        if indicator in final_url.lower():
            registration_success = True
            break

    # Check page content
    if not registration_success:
        try:
            page_text = await page.inner_text("body", timeout=5000)
            page_lower = page_text.lower()
            if any(x in page_lower for x in ["inbox", "welcome", "congratulations", "start using"]):
                registration_success = True
        except Exception:
            pass

    # Check if username was taken
    if not registration_success and "signup" in final_url.lower():
        try:
            error_text = await page.inner_text("body", timeout=3000)
            if "already used" in error_text.lower() or "not available" in error_text.lower():
                ctx._err(f"Username '{ctx.username}' already taken")
                raise RecoverableError("E105", f"Username '{ctx.username}' already taken")
        except RecoverableError:
            raise
        except Exception:
            pass

    if not registration_success:
        ctx._err(f"[FAIL] Registration NOT confirmed! URL: {final_url}")
        await _debug_screenshot(page, "proton_not_confirmed")
        raise FatalError("E502", f"Registration not confirmed: {final_url}")

    return True


# ── Main Orchestrator ────────────────────────────────────────────────────────────


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
    """Register a single ProtonMail account using the Defensive Coding Template."""
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
    username = username.replace("_", ".").lower()
    email = f"{username}@proton.me"

    # ── Create RegContext ──
    def _log(msg: str):
        n = getattr(thread_log, '_worker_id', 0) + 1 if thread_log else '?'
        logger.info(f"[ProtonMail][Thread {n}] {msg}")
        if thread_log:
            thread_log.current_action = f"Thread {n}: {msg}"
            try: db.commit()
            except Exception: pass

    def _err(msg: str):
        n = getattr(thread_log, '_worker_id', 0) + 1 if thread_log else '?'
        logger.error(f"[ProtonMail][Thread {n}] {msg}")
        if thread_log:
            thread_log.error_message = f"Thread {n}: {msg}"[:500]
            try: db.commit()
            except Exception: pass

    _proxy_geo = (proxy.geo or "").upper() if proxy else ""
    ctx = RegContext(
        provider="protonmail",
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

    context = await browser_manager.create_context(proxy=proxy, geo=None)

    try:
        page = await context.new_page()
        ACTIVE_PAGES[ctx.thread_id] = {"page": page, "context": context}

        # ── Execute Steps ──
        await step_0_warmup(page, ctx)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        await step_1_navigate(page, ctx, proxy, db)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        await step_2_select_plan(page, ctx)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        await step_3_username(page, ctx)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        await step_4_password(page, ctx)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        await step_5_submit(page, ctx)

        if BIRTH_CANCEL_EVENT.is_set():
            return None

        await step_6_captcha(page, ctx)

        await step_7_skip_recovery(page, ctx)

        await step_8_verify_success(page, ctx)

        # ── Save session, fingerprint, and create account ──
        account = Account(
            email=email,
            password=password,
            provider="protonmail",
            first_name=first_name,
            last_name=last_name,
            gender="random",
            birthday=birthday,
            geo=proxy.geo if proxy and hasattr(proxy, 'geo') else None,
            language=ctx.language or 'en',
            birth_ip=f"{proxy.host}" if proxy else None,
            status="new",
        )
        db.add(account)
        db.commit()
        db.refresh(account)

        # Save session (cookies/localStorage) with real account ID
        try:
            account.browser_profile_path = await browser_manager.save_session(context, account.id)
            db.commit()
        except Exception as se:
            logger.warning(f"[ProtonMail] Session save warning: {se}")

        # Save fingerprint for profile persistence
        try:
            fp_data = getattr(context, '_leomail_fingerprint', None)
            if fp_data:
                browser_manager.save_fingerprint(account.id, fp_data)
                account.user_agent = fp_data.get("user_agent", "")
                db.commit()
                logger.info(f"[ProtonMail] Fingerprint saved for account {account.id}")
        except Exception as fp_err:
            logger.warning(f"[ProtonMail] Fingerprint save warning: {fp_err}")

        logger.info(f"[OK] ProtonMail registered: {email}")
        export_account_to_file(account)

        # IMAP verification (non-blocking)
        try:
            from ...services.imap_checker import verify_account_imap
            await verify_account_imap(account, db, _log, _err)
        except Exception as imap_e:
            logger.debug(f"[ProtonMail] IMAP check skipped: {imap_e}")

        # Post-registration warmup
        try:
            from ..human_behavior import post_registration_warmup
            _log("[OK] Post-reg session warmup...")
            await post_registration_warmup(page, provider="protonmail")
        except Exception as warmup_e:
            logger.debug(f"[ProtonMail] Post-reg warmup error: {warmup_e}")

        return account

    except (RateLimitError, BannedIPError, CaptchaFailError, FatalError, RecoverableError):
        # Let typed errors propagate to BlitzEngine's structured handler
        raise
    except Exception as e:
        logger.error(f"[FAIL] ProtonMail registration failed: {e}", exc_info=True)
        _err(str(e)[:500])
        raise FatalError("E599", f"Unhandled: {str(e)[:200]}")
    finally:
        ACTIVE_PAGES.pop(ctx.thread_id, None)
        try:
            await context.close()
        except Exception:
            pass
