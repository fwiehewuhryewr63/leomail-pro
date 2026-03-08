"""
Leomail v4 - Browser Re-Login Module
Automatic re-login when saved session cookies expire.

Used by both Warmup and Campaign engines when is_login_page() detects
a redirect to the provider's login page.

Each provider has its own login flow with defensive multi-selector patterns
(same approach as birth providers — /Adaptor skill).

Returns True on successful re-login, False if login failed or 2FA/CAPTCHA detected.
"""
import asyncio
import random
from loguru import logger

from .birth._helpers import (
    human_fill, human_click, human_delay,
)


# ── Shared helpers ────────────────────────────────────────────────────────────

async def _wait_for_any(page, selectors: list[str], timeout: int = 10000) -> str | None:
    """Wait for any selector from list to appear. Returns first found selector or None."""
    end_time = asyncio.get_event_loop().time() + timeout / 1000
    while asyncio.get_event_loop().time() < end_time:
        for sel in selectors:
            try:
                if await page.locator(sel).first.is_visible(timeout=200):
                    return sel
            except Exception:
                continue
        await asyncio.sleep(0.3)
    return None


async def _detect_2fa_or_captcha(page) -> bool:
    """Detect if login flow requires 2FA, SMS verification, or CAPTCHA.
    If detected, re-login is impossible without external intervention."""
    indicators = [
        # 2FA / Phone verification
        'input[name="otc"]',              # Outlook OTC (one-time code)
        'input[name="iOttText"]',         # Outlook OTP
        '#idTxtBx_SAOTCC_OTC',            # Outlook authenticator
        'input[name="verify_code"]',      # Generic verify code
        'input[id="verification-code"]',  # Proton 2FA
        '#challenge-selector',            # Yahoo challenge selector
        'input[name="code"]',             # Generic 2FA code input

        # SMS verification
        'a[data-bind*="SMS"]',             # Outlook SMS option
        '#idDiv_SAOTCS_Proofs',            # Outlook security proofs list
        'input[name="phoneNumber"]',       # Phone number entry

        # CAPTCHA
        'iframe[src*="captcha"]',
        'iframe[src*="hsprotect"]',
        'iframe[title*="captcha"]',
        '#captcha-container',
        '.g-recaptcha',
        'iframe[src*="recaptcha"]',
        'iframe[src*="hcaptcha"]',

        # Security questions / identity verification
        '#iSelectProofTitle',              # Outlook "prove it's you"
        'div[data-testid="challenge"]',    # Yahoo challenge
    ]
    for sel in indicators:
        try:
            if await page.locator(sel).first.is_visible(timeout=500):
                logger.warning(f"[Re-Login] 2FA/CAPTCHA detected: {sel}")
                return True
        except Exception:
            continue
    return False


async def _verify_inbox_loaded(page, provider: str, timeout: int = 15000) -> bool:
    """Verify that we've landed in the inbox after re-login."""
    from .browser_mail_sender import is_login_page

    inbox_indicators = {
        "outlook": [
            '[aria-label="New mail"]',
            'button:has-text("New mail")',
            '[aria-label="Mail"]',
            'div[role="main"]',
        ],
        "hotmail": [
            '[aria-label="New mail"]',
            'button:has-text("New mail")',
        ],
        "yahoo": [
            'button[aria-label="New message"]',
            'a[data-test-id="compose-button"]',
            '#mail-app',
        ],
        "aol": [
            'a[data-test-id="compose-button"]',
            'button:has-text("Compose")',
        ],
        "gmail": [
            '[gh="cm"]',
            '[data-tooltip="Compose"]',
            'div[role="navigation"]',
        ],
        "protonmail": [
            '[data-testid="sidebar:compose"]',
            'button:has-text("New message")',
        ],
        "proton": [
            '[data-testid="sidebar:compose"]',
            'button:has-text("New message")',
        ],
    }

    selectors = inbox_indicators.get(provider, inbox_indicators.get("outlook", []))

    end_time = asyncio.get_event_loop().time() + timeout / 1000
    while asyncio.get_event_loop().time() < end_time:
        # Check URL first — fast signal
        if not is_login_page(page.url):
            # Check for inbox elements
            for sel in selectors:
                try:
                    if await page.locator(sel).first.is_visible(timeout=300):
                        return True
                except Exception:
                    continue
        await asyncio.sleep(1.0)

    return False


# ── Outlook / Hotmail ─────────────────────────────────────────────────────────

async def _relogin_outlook(page, email: str, password: str) -> bool:
    """Re-login to Outlook/Hotmail via browser.
    Flow: email field → Next → password field → Next → Stay signed in? → Yes
    """
    logger.info(f"[Re-Login] Outlook: {email}")

    # Step 1: Email field
    email_selectors = [
        'input[name="loginfmt"]',
        'input[type="email"]',
        '#i0116',
        'input[aria-label*="email"]',
        'input[aria-label*="phone"]',
        'input[placeholder*="email"]',
        'input[placeholder*="phone"]',
    ]
    found = await _wait_for_any(page, email_selectors, timeout=10000)
    if not found:
        logger.warning("[Re-Login] Outlook: email field not found")
        return False

    await human_fill(page, found, email)
    await human_delay(0.5, 1.0)

    # Click Next
    next_selectors = [
        '#idSIButton9',
        'input[type="submit"]',
        'button[type="submit"]',
        'input[value="Next"]',
        'button:has-text("Next")',
        'button:has-text("Далее")',
    ]
    next_btn = await _wait_for_any(page, next_selectors, timeout=3000)
    if next_btn:
        await human_click(page, next_btn)
    else:
        await page.keyboard.press("Enter")
    await human_delay(2, 4)

    # Check for 2FA/CAPTCHA after email
    if await _detect_2fa_or_captcha(page):
        return False

    # Step 2: Password field
    pwd_selectors = [
        'input[name="passwd"]',
        'input[type="password"]',
        '#i0118',
        'input[aria-label*="assword"]',
        'input[placeholder*="assword"]',
        '#passwordInput',
    ]
    found_pwd = await _wait_for_any(page, pwd_selectors, timeout=10000)
    if not found_pwd:
        logger.warning("[Re-Login] Outlook: password field not found")
        # Maybe account picker appeared — try clicking the account first
        try:
            acct_tile = page.locator(f'div[data-test-id="{email}"], li:has-text("{email}")')
            if await acct_tile.first.is_visible(timeout=2000):
                await acct_tile.first.click()
                await human_delay(2, 3)
                found_pwd = await _wait_for_any(page, pwd_selectors, timeout=8000)
        except Exception:
            pass
        if not found_pwd:
            return False

    await human_fill(page, found_pwd, password)
    await human_delay(0.5, 1.0)

    # Click Sign In
    signin_selectors = [
        '#idSIButton9',
        'input[type="submit"]',
        'button[type="submit"]',
        'input[value="Sign in"]',
        'button:has-text("Sign in")',
        'button:has-text("Войти")',
    ]
    sign_btn = await _wait_for_any(page, signin_selectors, timeout=3000)
    if sign_btn:
        await human_click(page, sign_btn)
    else:
        await page.keyboard.press("Enter")
    await human_delay(3, 6)

    # Check for 2FA after password
    if await _detect_2fa_or_captcha(page):
        return False

    # Check for wrong password error
    error_selectors = [
        '#passwordError',
        '#usernameError',
        'div[role="alert"]',
        '#error_0_passwd',
    ]
    for sel in error_selectors:
        try:
            if await page.locator(sel).first.is_visible(timeout=1000):
                err_text = await page.locator(sel).first.inner_text()
                logger.warning(f"[Re-Login] Outlook: login error: {err_text[:100]}")
                return False
        except Exception:
            continue

    # Step 3: "Stay signed in?" → Yes (critical for session persistence!)
    stay_selectors = [
        '#idSIButton9',  # "Yes" on KMSI page
        '#acceptButton',
        'input[value="Yes"]',
        'button:has-text("Yes")',
        'button:has-text("Да")',
    ]
    stay_btn = await _wait_for_any(page, stay_selectors, timeout=5000)
    if stay_btn:
        await human_click(page, stay_btn)
        await human_delay(3, 5)

    return True


# ── Yahoo / AOL ───────────────────────────────────────────────────────────────

async def _relogin_yahoo(page, email: str, password: str) -> bool:
    """Re-login to Yahoo/AOL via browser.
    Flow: username → Next → password → Next
    """
    logger.info(f"[Re-Login] Yahoo/AOL: {email}")

    # Step 1: Username field
    username_selectors = [
        '#login-username',
        'input[name="username"]',
        'input[type="text"]#login-username',
        'input[placeholder*="username"]',
        'input[placeholder*="email"]',
        'input[aria-label*="Username"]',
        'input[aria-label*="Email"]',
    ]
    found = await _wait_for_any(page, username_selectors, timeout=10000)
    if not found:
        logger.warning("[Re-Login] Yahoo: username field not found")
        return False

    await human_fill(page, found, email)
    await human_delay(0.5, 1.0)

    # Click Next
    next_selectors = [
        '#login-signin',
        'button[name="signin"]',
        'input[name="signin"]',
        'button:has-text("Next")',
        'button:has-text("Sign in")',
    ]
    next_btn = await _wait_for_any(page, next_selectors, timeout=3000)
    if next_btn:
        await human_click(page, next_btn)
    else:
        await page.keyboard.press("Enter")
    await human_delay(2, 4)

    # Check for 2FA/challenge
    if await _detect_2fa_or_captcha(page):
        return False

    # Step 2: Password field
    pwd_selectors = [
        '#login-passwd',
        'input[name="password"]',
        'input[type="password"]',
        'input[placeholder*="password"]',
        'input[aria-label*="Password"]',
    ]
    found_pwd = await _wait_for_any(page, pwd_selectors, timeout=10000)
    if not found_pwd:
        logger.warning("[Re-Login] Yahoo: password field not found")
        return False

    await human_fill(page, found_pwd, password)
    await human_delay(0.5, 1.0)

    # Click Sign In
    signin_selectors = [
        '#login-signin',
        'button[name="signin"]',
        'input[name="signin"]',
        'button:has-text("Sign in")',
        'button:has-text("Next")',
    ]
    sign_btn = await _wait_for_any(page, signin_selectors, timeout=3000)
    if sign_btn:
        await human_click(page, sign_btn)
    else:
        await page.keyboard.press("Enter")
    await human_delay(3, 6)

    # Check for 2FA/challenge after password
    if await _detect_2fa_or_captcha(page):
        return False

    # Check for error messages
    try:
        error_el = page.locator('#username-error, .error-msg, [data-error]')
        if await error_el.first.is_visible(timeout=2000):
            err_text = await error_el.first.inner_text()
            logger.warning(f"[Re-Login] Yahoo: login error: {err_text[:100]}")
            return False
    except Exception:
        pass

    return True


# ── Gmail ─────────────────────────────────────────────────────────────────────

async def _relogin_gmail(page, email: str, password: str) -> bool:
    """Re-login to Gmail via browser.
    Flow: email → Next → password → Next
    Note: Gmail may show account picker, device verification, or 2FA.
    """
    logger.info(f"[Re-Login] Gmail: {email}")

    # Step 1: Email field (or account picker)
    email_selectors = [
        'input[type="email"]',
        '#identifierId',
        'input[name="identifier"]',
        'input[aria-label*="Email"]',
        'input[aria-label*="Phone"]',
    ]
    found = await _wait_for_any(page, email_selectors, timeout=8000)
    if not found:
        # Maybe account picker — try clicking "Use another account"
        try:
            another = page.locator('div:has-text("Use another account"), div:has-text("Другой аккаунт")')
            if await another.first.is_visible(timeout=2000):
                await another.first.click()
                await human_delay(2, 3)
                found = await _wait_for_any(page, email_selectors, timeout=5000)
        except Exception:
            pass
        if not found:
            logger.warning("[Re-Login] Gmail: email field not found")
            return False

    await human_fill(page, found, email)
    await human_delay(0.5, 1.0)

    # Click Next
    next_selectors = [
        '#identifierNext',
        'button:has-text("Next")',
        'button:has-text("Далее")',
        'div[id="identifierNext"] button',
    ]
    next_btn = await _wait_for_any(page, next_selectors, timeout=3000)
    if next_btn:
        await human_click(page, next_btn)
    else:
        await page.keyboard.press("Enter")
    await human_delay(3, 5)

    # Check for 2FA / device verification (very common with Gmail)
    if await _detect_2fa_or_captcha(page):
        return False

    # Step 2: Password
    pwd_selectors = [
        'input[type="password"]',
        'input[name="Passwd"]',
        '#password input',
        'input[aria-label*="assword"]',
    ]
    found_pwd = await _wait_for_any(page, pwd_selectors, timeout=10000)
    if not found_pwd:
        logger.warning("[Re-Login] Gmail: password field not found (likely device verification)")
        return False

    await human_fill(page, found_pwd, password)
    await human_delay(0.5, 1.0)

    # Click Next
    pwd_next_selectors = [
        '#passwordNext',
        'button:has-text("Next")',
        'button:has-text("Далее")',
        'div[id="passwordNext"] button',
    ]
    pwd_btn = await _wait_for_any(page, pwd_next_selectors, timeout=3000)
    if pwd_btn:
        await human_click(page, pwd_btn)
    else:
        await page.keyboard.press("Enter")
    await human_delay(3, 6)

    # Post-login 2FA check
    if await _detect_2fa_or_captcha(page):
        return False

    # Check for wrong password
    try:
        err = page.locator('[aria-label*="Wrong password"], span:has-text("Wrong password")')
        if await err.first.is_visible(timeout=2000):
            logger.warning("[Re-Login] Gmail: wrong password")
            return False
    except Exception:
        pass

    return True


# ── Proton Mail ───────────────────────────────────────────────────────────────

async def _relogin_proton(page, email: str, password: str) -> bool:
    """Re-login to Proton Mail via browser.
    Flow: email + password on same page → Sign in
    """
    logger.info(f"[Re-Login] Proton: {email}")

    # Proton has email + password on the same page
    email_selectors = [
        '#email',
        'input[id="email"]',
        'input[name="email"]',
        'input[type="email"]',
        'input[placeholder*="email"]',
        'input[placeholder*="Email"]',
    ]
    found_email = await _wait_for_any(page, email_selectors, timeout=10000)
    if not found_email:
        logger.warning("[Re-Login] Proton: email field not found")
        return False

    await human_fill(page, found_email, email)
    await human_delay(0.5, 1.0)

    # Password field
    pwd_selectors = [
        '#password',
        'input[id="password"]',
        'input[name="password"]',
        'input[type="password"]',
        'input[placeholder*="assword"]',
    ]
    found_pwd = await _wait_for_any(page, pwd_selectors, timeout=5000)
    if not found_pwd:
        logger.warning("[Re-Login] Proton: password field not found")
        return False

    await human_fill(page, found_pwd, password)
    await human_delay(0.5, 1.0)

    # Click Sign in
    signin_selectors = [
        'button[type="submit"]',
        'button:has-text("Sign in")',
        'button:has-text("Войти")',
        '[data-testid="submit"]',
    ]
    sign_btn = await _wait_for_any(page, signin_selectors, timeout=3000)
    if sign_btn:
        await human_click(page, sign_btn)
    else:
        await page.keyboard.press("Enter")
    await human_delay(3, 6)

    # Check for 2FA (Proton commonly uses TOTP)
    totp_selectors = [
        'input[id="twoFa"]',
        'input[name="twoFa"]',
        'input[placeholder*="Two-factor"]',
        '#verification-code',
    ]
    totp_found = await _wait_for_any(page, totp_selectors, timeout=3000)
    if totp_found:
        logger.warning("[Re-Login] Proton: 2FA (TOTP) required — cannot auto-solve")
        return False

    # Check for wrong password
    try:
        err = page.locator('[class*="error"], [role="alert"]')
        if await err.first.is_visible(timeout=2000):
            err_text = await err.first.inner_text()
            if "incorrect" in err_text.lower() or "wrong" in err_text.lower() or "invalid" in err_text.lower():
                logger.warning(f"[Re-Login] Proton: login error: {err_text[:100]}")
                return False
    except Exception:
        pass

    return True


# ── Main dispatcher ──────────────────────────────────────────────────────────

async def browser_relogin(page, provider: str, email: str, password: str) -> bool:
    """
    Attempt browser re-login for an account with expired session cookies.

    Args:
        page: Playwright Page (already on login page)
        provider: Account provider (outlook, yahoo, gmail, protonmail, etc.)
        email: Account email
        password: Account password

    Returns:
        True if re-login succeeded (inbox loaded), False if failed
    """
    if not email or not password:
        logger.warning(f"[Re-Login] Missing credentials for {provider}")
        return False

    try:
        # Route to provider-specific login flow
        if provider in ("outlook", "hotmail"):
            ok = await _relogin_outlook(page, email, password)
        elif provider in ("yahoo", "aol"):
            ok = await _relogin_yahoo(page, email, password)
        elif provider == "gmail":
            ok = await _relogin_gmail(page, email, password)
        elif provider in ("proton", "protonmail"):
            ok = await _relogin_proton(page, email, password)
        else:
            logger.warning(f"[Re-Login] Unsupported provider: {provider}")
            return False

        if not ok:
            logger.warning(f"[Re-Login] {provider} login flow failed for {email}")
            return False

        # Verify we actually landed in the inbox
        inbox_ok = await _verify_inbox_loaded(page, provider, timeout=20000)
        if inbox_ok:
            logger.info(f"[Re-Login] SUCCESS: {email} ({provider}) — inbox loaded")
            return True
        else:
            logger.warning(f"[Re-Login] {provider} {email}: login flow passed but inbox not loaded")
            return False

    except Exception as e:
        logger.error(f"[Re-Login] {provider} {email} error: {e}")
        return False
