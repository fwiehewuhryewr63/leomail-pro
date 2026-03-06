"""
Leomail v4 - Shared Browser Mail Sender
Extracted from campaign_engine.py for reuse by both Campaign and Warmup engines.
Provides browser-based compose & send for all supported providers.
"""
import asyncio
import random
from loguru import logger


# ── Webmail URLs per provider ────────────────────────────────────────────────

MAIL_URLS = {
    "yahoo": "https://mail.yahoo.com/",
    "aol": "https://mail.aol.com/",
    "gmail": "https://mail.google.com",
    "outlook": "https://outlook.live.com/mail",
    "hotmail": "https://outlook.live.com/mail",
    "protonmail": "https://mail.proton.me",
    "proton": "https://mail.proton.me",
}


# ── Main dispatcher ──────────────────────────────────────────────────────────

async def browser_compose_send(page, provider: str, to_email: str, subject: str, body: str):
    """
    Compose and send one email via browser UI.
    Raises Exception on failure (caller handles error classification).
    """
    if provider in ("yahoo", "aol"):
        await browser_send_yahoo_aol(page, to_email, subject, body, provider)
    elif provider in ("outlook", "hotmail"):
        await browser_send_outlook(page, to_email, subject, body)
    elif provider == "gmail":
        await browser_send_gmail(page, to_email, subject, body)
    elif provider in ("proton", "protonmail"):
        await browser_send_proton(page, to_email, subject, body)
    else:
        raise Exception(f"Browser send not implemented for provider: {provider}")


# ── Yahoo / AOL ──────────────────────────────────────────────────────────────

async def browser_send_yahoo_aol(
    page, to_email: str, subject: str, body: str, provider: str = "yahoo"
):
    """Compose and send in Yahoo/AOL Mail via browser."""
    if provider == "aol":
        compose_sel = 'a[data-test-id="compose-button"], button:has-text("Compose")'
    else:
        compose_sel = 'button[aria-label="New message"], a[data-test-id="compose-button"]'
    await page.locator(compose_sel).first.click(timeout=10000)
    await asyncio.sleep(random.uniform(1.5, 3))

    to_field = page.locator('input#message-to-field')
    await to_field.click()
    await asyncio.sleep(random.uniform(0.2, 0.5))
    await to_field.type(to_email, delay=random.randint(30, 70))
    await asyncio.sleep(random.uniform(0.3, 0.6))
    await page.keyboard.press("Tab")
    await asyncio.sleep(random.uniform(0.5, 1))

    subj_field = page.locator('input#compose-subject-input')
    await subj_field.click()
    await subj_field.fill("")
    await subj_field.type(subject, delay=random.randint(20, 50))
    await asyncio.sleep(random.uniform(0.3, 0.8))

    body_field = page.locator('div[aria-label="Message body"]')
    await body_field.click()
    if "<" in body:
        await page.evaluate(
            "(el, html) => el.innerHTML = html",
            [await body_field.element_handle(), body],
        )
    else:
        await body_field.type(body, delay=random.randint(10, 30))
    await asyncio.sleep(random.uniform(0.5, 1.5))

    for sel in [
        'button[aria-label="Send this email"]',
        'button[title="Send this email"]',
        'button:has-text("Send")',
    ]:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=1000):
                await btn.click()
                break
        except Exception:
            continue

    await asyncio.sleep(random.uniform(2, 4))

    page_text = await page.inner_text("body")
    if "limit" in page_text.lower() or "too many" in page_text.lower():
        raise Exception("Daily sending limit detected")
    if "temporarily locked" in page_text.lower():
        raise Exception("Account temporarily locked")


# ── Gmail ─────────────────────────────────────────────────────────────────────

async def browser_send_gmail(page, to_email: str, subject: str, body: str):
    """Compose and send in Gmail via browser."""
    await page.click('[gh="cm"], [data-tooltip="Compose"]', timeout=10000)
    await asyncio.sleep(random.uniform(1, 2.5))

    to_input = page.locator('input[name="to"], [aria-label="To recipients"]').first
    await to_input.click()
    await to_input.type(to_email, delay=random.randint(30, 60))
    await asyncio.sleep(random.uniform(0.5, 1.5))

    subj_input = page.locator('input[name="subjectbox"]').first
    await subj_input.click()
    await subj_input.type(subject, delay=random.randint(20, 50))
    await asyncio.sleep(random.uniform(0.3, 1))

    body_el = page.locator('[aria-label="Message Body"], [role="textbox"]').first
    await body_el.click()
    if "<" in body:
        await page.evaluate(
            "(el, html) => el.innerHTML = html",
            [await body_el.element_handle(), body],
        )
    else:
        await body_el.type(body, delay=random.randint(10, 30))
    await asyncio.sleep(random.uniform(0.5, 2))

    await page.click('[aria-label="Send"], [data-tooltip="Send"]')
    await asyncio.sleep(random.uniform(2, 4))


# ── Outlook / Hotmail ─────────────────────────────────────────────────────────

async def browser_send_outlook(page, to_email: str, subject: str, body: str):
    """Compose and send in Outlook/Hotmail via browser."""
    await page.click('[aria-label="New mail"], button:has-text("New mail")', timeout=10000)
    await asyncio.sleep(random.uniform(1, 3))

    to_input = page.locator('[aria-label="To"], input[role="combobox"]').first
    await to_input.click()
    await to_input.type(to_email, delay=random.randint(30, 60))
    await asyncio.sleep(random.uniform(1, 2))
    await page.keyboard.press("Tab")

    subj_input = page.locator('[aria-label="Add a subject"]').first
    await subj_input.click()
    await subj_input.type(subject, delay=random.randint(20, 50))
    await asyncio.sleep(random.uniform(0.3, 1))

    body_el = page.locator('[aria-label="Message body"], [role="textbox"]').first
    await body_el.click()
    if "<" in body:
        await page.evaluate(
            "(el, html) => el.innerHTML = html",
            [await body_el.element_handle(), body],
        )
    else:
        await body_el.type(body, delay=random.randint(10, 30))
    await asyncio.sleep(random.uniform(0.5, 2))

    await page.click('[aria-label="Send"], button:has-text("Send")')
    await asyncio.sleep(random.uniform(2, 4))


# ── Proton Mail ───────────────────────────────────────────────────────────────

async def browser_send_proton(page, to_email: str, subject: str, body: str):
    """Compose and send in Proton Mail via browser."""
    await page.click('[data-testid="sidebar:compose"], button:has-text("New message")', timeout=10000)
    await asyncio.sleep(random.uniform(1, 3))

    to_input = page.locator('[data-testid="composer:to"] input, input[placeholder*="Recipient"]').first
    await to_input.click()
    await to_input.type(to_email, delay=random.randint(30, 60))
    await asyncio.sleep(random.uniform(0.5, 1))
    await page.keyboard.press("Tab")
    await asyncio.sleep(random.uniform(0.3, 0.6))

    subj_input = page.locator('[data-testid="composer:subject"] input, input[placeholder="Subject"]').first
    await subj_input.click()
    await subj_input.type(subject, delay=random.randint(20, 50))
    await asyncio.sleep(random.uniform(0.3, 1))

    body_el = page.locator('[data-testid="composer:body"] [contenteditable="true"], [contenteditable="true"]').first
    await body_el.click()
    if "<" in body:
        await page.evaluate(
            "(el, html) => el.innerHTML = html",
            [await body_el.element_handle(), body],
        )
    else:
        await body_el.type(body, delay=random.randint(10, 30))
    await asyncio.sleep(random.uniform(0.5, 2))

    await page.click('[data-testid="composer:send-button"], button:has-text("Send")')
    await asyncio.sleep(random.uniform(2, 5))


# ── Session validation helper ─────────────────────────────────────────────────

def is_login_page(url: str) -> bool:
    """Check if current URL indicates we're on a login/signin page (session expired)."""
    login_indicators = ["signin", "login", "account.live", "accounts.google", "signup"]
    url_lower = url.lower()
    return any(ind in url_lower for ind in login_indicators)
