"""
Leomail v4 - Browser Mail Actions
Inbox interactions for warmup: read emails, reply, star, mark important, spam rescue.
Complements browser_mail_sender.py (compose & send).
All actions use human-like delays and follow Adaptor/Stealth patterns.
"""
import asyncio
import random
from loguru import logger


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _wait_for_any(page, selectors: list[str], timeout: int = 8000):
    """Wait for any of the selectors to appear. Returns (locator, selector) or (None, None)."""
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if await loc.is_visible(timeout=timeout // len(selectors)):
                return loc, sel
        except Exception:
            continue
    return None, None


async def _human_pause(min_s: float = 0.5, max_s: float = 2.0):
    """Human-like pause between actions."""
    await asyncio.sleep(random.uniform(min_s, max_s))


# ── Read inbox emails ────────────────────────────────────────────────────────

async def read_inbox_emails(page, provider: str, max_emails: int = 3) -> list:
    """
    Read (open + scroll) emails in inbox. Returns list of email info dicts.
    Each dict has: {'index': int, 'subject': str} for use in follow-up actions.
    """
    try:
        # Ensure we're on inbox
        await _navigate_to_inbox(page, provider)
        await _human_pause(1.5, 3.0)

        # Get email list items
        email_items = await _get_email_list_items(page, provider)
        if not email_items:
            logger.debug(f"[Warmup] No emails in inbox for {provider}")
            return []

        read_count = min(max_emails, len(email_items))
        results = []

        for i in range(read_count):
            try:
                item = email_items[i]
                # Click to open email
                await item.click(timeout=5000)
                await _human_pause(2.0, 4.0)

                # Scroll through email body (human reads)
                await _scroll_email(page)
                await _human_pause(1.0, 3.0)

                results.append({"index": i, "subject": f"email_{i}"})

                # Go back to inbox list
                await _go_back_to_inbox(page, provider)
                await _human_pause(1.0, 2.0)

            except Exception as e:
                logger.debug(f"[Warmup] Failed to read email {i}: {e}")
                try:
                    await _go_back_to_inbox(page, provider)
                except Exception:
                    pass
                continue

        logger.debug(f"[Warmup] Read {len(results)} emails in {provider} inbox")
        return results

    except Exception as e:
        logger.warning(f"[Warmup] read_inbox_emails failed ({provider}): {e}")
        return []


# ── Reply to email ───────────────────────────────────────────────────────────

async def reply_to_email(page, provider: str, email_index: int, reply_text: str) -> bool:
    """
    Open email by index and reply to it.
    Must be called from inbox view.
    """
    try:
        # Get email items and click the one we want
        email_items = await _get_email_list_items(page, provider)
        if email_index >= len(email_items):
            return False

        await email_items[email_index].click(timeout=5000)
        await _human_pause(1.5, 3.0)

        # Click Reply button
        reply_clicked = await _click_reply_button(page, provider)
        if not reply_clicked:
            await _go_back_to_inbox(page, provider)
            return False

        await _human_pause(1.0, 2.5)

        # Type reply text
        reply_typed = await _type_reply_text(page, provider, reply_text)
        if not reply_typed:
            await _go_back_to_inbox(page, provider)
            return False

        await _human_pause(0.5, 1.5)

        # Click Send
        await _click_send_button(page, provider)
        await _human_pause(2.0, 4.0)

        # Go back to inbox
        await _go_back_to_inbox(page, provider)

        logger.debug(f"[Warmup] Replied to email {email_index} via {provider}")
        return True

    except Exception as e:
        logger.warning(f"[Warmup] reply_to_email failed ({provider}): {e}")
        try:
            await _go_back_to_inbox(page, provider)
        except Exception:
            pass
        return False


# ── Mark as starred ──────────────────────────────────────────────────────────

async def mark_as_starred(page, provider: str, email_index: int) -> bool:
    """Toggle star on email in inbox list (without opening it)."""
    try:
        email_items = await _get_email_list_items(page, provider)
        if email_index >= len(email_items):
            return False

        item = email_items[email_index]

        if provider in ("yahoo", "aol"):
            star, _ = await _wait_for_any(item, [
                'button[aria-label*="tar"]',
                'button[title*="tar"]',
                'span[data-test-id="icon-btn-star"]',
            ], timeout=3000)
        elif provider == "gmail":
            star, _ = await _wait_for_any(item, [
                'span.T-KT',
                '[aria-label*="tar"]',
                'img[alt="Not starred"]',
            ], timeout=3000)
        elif provider in ("outlook", "hotmail"):
            star, _ = await _wait_for_any(item, [
                'button[aria-label*="lag"]',
                'button[title*="lag"]',
                '[aria-label*="Flag"]',
            ], timeout=3000)
        elif provider in ("proton", "protonmail"):
            star, _ = await _wait_for_any(item, [
                'button[data-testid="item-star"]',
                '[aria-label*="tar"]',
                'button[title*="tar"]',
            ], timeout=3000)
        elif provider == "webde":
            star, _ = await _wait_for_any(item, [
                'button[aria-label*="terne"]',
                'button[aria-label*="star"]',
                'button[title*="Kennzeichnung"]',
                '[aria-label*="Kennzeich"]',
            ], timeout=3000)
        else:
            return False

        if star:
            await star.click()
            await _human_pause(0.3, 1.0)
            logger.debug(f"[Warmup] Starred email {email_index} in {provider}")
            return True

        return False

    except Exception as e:
        logger.debug(f"[Warmup] mark_as_starred failed ({provider}): {e}")
        return False


# ── Mark as important ────────────────────────────────────────────────────────

async def mark_as_important(page, provider: str, email_index: int) -> bool:
    """
    Mark email as important. Only supported by Gmail and Outlook.
    Yahoo/AOL/Proton don't have native 'important' markers.
    """
    try:
        if provider in ("yahoo", "aol", "proton", "protonmail", "webde"):
            # These providers don't have an important marker — use star instead
            return await mark_as_starred(page, provider, email_index)

        email_items = await _get_email_list_items(page, provider)
        if email_index >= len(email_items):
            return False

        item = email_items[email_index]

        if provider == "gmail":
            imp, _ = await _wait_for_any(item, [
                '[aria-label*="mportant"]',
                'span.pH',
                '[data-tooltip*="mportant"]',
            ], timeout=3000)
        elif provider in ("outlook", "hotmail"):
            # Outlook uses "flag" as important equivalent — right-click for importance
            imp, _ = await _wait_for_any(item, [
                'button[aria-label*="mportance"]',
                'button[title*="mportance"]',
            ], timeout=3000)
        else:
            return False

        if imp:
            await imp.click()
            await _human_pause(0.3, 1.0)
            logger.debug(f"[Warmup] Marked email {email_index} as important in {provider}")
            return True

        return False

    except Exception as e:
        logger.debug(f"[Warmup] mark_as_important failed ({provider}): {e}")
        return False


# ── Rescue from spam ─────────────────────────────────────────────────────────

async def rescue_from_spam(page, provider: str, max_emails: int = 2) -> int:
    """
    Navigate to spam/junk folder, move warmup emails back to inbox.
    Returns count of rescued emails.
    """
    rescued = 0
    try:
        await _navigate_to_spam(page, provider)
        await _human_pause(1.5, 3.0)

        email_items = await _get_email_list_items(page, provider)
        if not email_items:
            logger.debug(f"[Warmup] No emails in spam for {provider}")
            await _navigate_to_inbox(page, provider)
            return 0

        rescue_count = min(max_emails, len(email_items))

        for i in range(rescue_count):
            try:
                items = await _get_email_list_items(page, provider)
                if not items:
                    break
                await items[0].click(timeout=5000)
                await _human_pause(1.0, 2.0)

                not_spam_clicked = await _click_not_spam(page, provider)
                if not_spam_clicked:
                    rescued += 1
                    await _human_pause(1.0, 2.0)
                else:
                    await _go_back_to_inbox(page, provider)
                    await _navigate_to_spam(page, provider)
                    await _human_pause(1.0, 2.0)

            except Exception as e:
                logger.debug(f"[Warmup] Failed to rescue email from spam: {e}")
                break

        # Go back to inbox
        await _navigate_to_inbox(page, provider)

        if rescued > 0:
            logger.debug(f"[Warmup] Rescued {rescued} emails from spam in {provider}")

    except Exception as e:
        logger.warning(f"[Warmup] rescue_from_spam failed ({provider}): {e}")
        try:
            await _navigate_to_inbox(page, provider)
        except Exception:
            pass

    return rescued


# ══════════════════════════════════════════════════════════════════════════════
# INTERNAL HELPERS — Provider-specific navigation and selectors
# ══════════════════════════════════════════════════════════════════════════════


async def _navigate_to_inbox(page, provider: str):
    """Click on Inbox folder in sidebar."""
    if provider in ("yahoo", "aol"):
        loc, _ = await _wait_for_any(page, [
            'a[data-test-folder-container="Inbox"]',
            'a[title="Inbox"]',
            '[data-test-id="folder-list-item-Inbox"]',
            'a:has-text("Inbox")',
        ], timeout=5000)
    elif provider == "gmail":
        loc, _ = await _wait_for_any(page, [
            'a[href*="#inbox"]',
            '[data-tooltip="Inbox"]',
            'a[title="Inbox"]',
            'span:has-text("Inbox")',
        ], timeout=5000)
    elif provider in ("outlook", "hotmail"):
        loc, _ = await _wait_for_any(page, [
            '[title="Inbox"]',
            '[aria-label="Inbox"]',
            'span:has-text("Inbox")',
        ], timeout=5000)
    elif provider in ("proton", "protonmail"):
        loc, _ = await _wait_for_any(page, [
            '[data-testid="navigation-link:inbox"]',
            'a[title="Inbox"]',
            '[href="/inbox"]',
        ], timeout=5000)
    elif provider == "webde":
        loc, _ = await _wait_for_any(page, [
            'a:has-text("Posteingang")',
            '[aria-label="Posteingang"]',
            'a[title="Posteingang"]',
            'a:has-text("Inbox")',
        ], timeout=5000)
    else:
        return

    if loc:
        await loc.click()
        await _human_pause(1.0, 2.0)


async def _navigate_to_spam(page, provider: str):
    """Click on Spam/Junk folder in sidebar."""
    if provider in ("yahoo", "aol"):
        loc, _ = await _wait_for_any(page, [
            'a[data-test-folder-container="Bulk"]',
            'a[title="Spam"]',
            'a[title="Bulk Mail"]',
            'a:has-text("Spam")',
        ], timeout=5000)
    elif provider == "gmail":
        loc, _ = await _wait_for_any(page, [
            'a[href*="#spam"]',
            '[data-tooltip="Spam"]',
            'a[title="Spam"]',
        ], timeout=5000)
    elif provider in ("outlook", "hotmail"):
        loc, _ = await _wait_for_any(page, [
            '[title="Junk Email"]',
            '[aria-label="Junk Email"]',
            'span:has-text("Junk")',
        ], timeout=5000)
    elif provider in ("proton", "protonmail"):
        loc, _ = await _wait_for_any(page, [
            '[data-testid="navigation-link:spam"]',
            'a[title="Spam"]',
            '[href="/spam"]',
        ], timeout=5000)
    elif provider == "webde":
        loc, _ = await _wait_for_any(page, [
            'a:has-text("Spam")',
            '[aria-label="Spam"]',
            'a[title="Spam"]',
            'a:has-text("Junk")',
        ], timeout=5000)
    else:
        return

    if loc:
        await loc.click()
        await _human_pause(1.0, 2.0)


async def _get_email_list_items(page, provider: str) -> list:
    """Get list of visible email items in current folder."""
    if provider in ("yahoo", "aol"):
        selectors = [
            'a[data-test-id="message-list-item"]',
            'li[data-test-id="message-list-item"]',
            '[data-test-id="message-group-item"]',
        ]
    elif provider == "gmail":
        selectors = [
            'tr.zA',
            'div[role="row"]',
            'tr[jscontroller]',
        ]
    elif provider in ("outlook", "hotmail"):
        selectors = [
            'div[role="option"][aria-label]',
            'div[data-convid]',
            '[aria-label*="onversation"]',
        ]
    elif provider in ("proton", "protonmail"):
        selectors = [
            '[data-testid="message-item"]',
            '[data-testid="message-item:unread"]',
            'div[data-element-id]',
        ]
    elif provider == "webde":
        selectors = [
            'tr[class*="mail-list"]',
            'li[class*="mail-item"]',
            'div[data-testid="mail-item"]',
            'tr[class*="item"]',
            'a[class*="mail-list"]',
        ]
    else:
        return []

    for sel in selectors:
        try:
            count = await page.locator(sel).count()
            if count > 0:
                return [page.locator(sel).nth(i) for i in range(min(count, 10))]
        except Exception:
            continue

    return []


async def _scroll_email(page):
    """Scroll through email body like a human reading."""
    try:
        for _ in range(random.randint(1, 3)):
            await page.mouse.wheel(0, random.randint(100, 300))
            await _human_pause(0.5, 1.5)
    except Exception:
        pass


async def _go_back_to_inbox(page, provider: str):
    """Go back from email detail view to inbox list."""
    if provider in ("yahoo", "aol"):
        loc, _ = await _wait_for_any(page, [
            'button[aria-label="Back"]',
            'button[title="Back to Inbox"]',
            'a[data-test-folder-container="Inbox"]',
        ], timeout=3000)
    elif provider == "gmail":
        loc, _ = await _wait_for_any(page, [
            '[aria-label="Back to Inbox"]',
            '[data-tooltip="Back to Inbox"]',
            'a[href*="#inbox"]',
        ], timeout=3000)
    elif provider in ("outlook", "hotmail"):
        # Outlook uses reading pane — might not need to go back
        loc, _ = await _wait_for_any(page, [
            'button[aria-label="Back"]',
            '[title="Inbox"]',
        ], timeout=3000)
    elif provider in ("proton", "protonmail"):
        loc, _ = await _wait_for_any(page, [
            'button[data-testid="toolbar:back-button"]',
            '[aria-label="Back"]',
            '[data-testid="navigation-link:inbox"]',
        ], timeout=3000)
    elif provider == "webde":
        loc, _ = await _wait_for_any(page, [
            'a:has-text("Posteingang")',
            'button[aria-label*="Zurück"]',
            'button[aria-label="Back"]',
            '[aria-label="Posteingang"]',
        ], timeout=3000)
    else:
        return

    if loc:
        await loc.click()
        await _human_pause(0.5, 1.5)


async def _click_reply_button(page, provider: str) -> bool:
    """Click Reply button in email detail view."""
    if provider in ("yahoo", "aol"):
        selectors = [
            'button[aria-label="Reply"]',
            'button[title="Reply"]',
            'button:has-text("Reply")',
        ]
    elif provider == "gmail":
        selectors = [
            '[aria-label="Reply"]',
            '[data-tooltip="Reply"]',
            'span[role="link"]:has-text("Reply")',
        ]
    elif provider in ("outlook", "hotmail"):
        selectors = [
            'button[aria-label="Reply"]',
            'button[title="Reply"]',
            'button:has-text("Reply")',
        ]
    elif provider in ("proton", "protonmail"):
        selectors = [
            '[data-testid="toolbar:reply"]',
            'button[aria-label="Reply"]',
            'button:has-text("Reply")',
        ]
    elif provider == "webde":
        selectors = [
            'button:has-text("Antworten")',
            'button[aria-label*="Antworten"]',
            'button[title*="Antworten"]',
            'button:has-text("Reply")',
        ]
    else:
        return False

    loc, _ = await _wait_for_any(page, selectors, timeout=5000)
    if loc:
        await loc.click()
        return True
    return False


async def _type_reply_text(page, provider: str, text: str) -> bool:
    """Type text into the reply compose area."""
    if provider in ("yahoo", "aol"):
        selectors = [
            'div[aria-label="Message body"]',
            'div[contenteditable="true"]',
        ]
    elif provider == "gmail":
        selectors = [
            '[aria-label="Message Body"]',
            'div[role="textbox"]',
            'div[contenteditable="true"]',
        ]
    elif provider in ("outlook", "hotmail"):
        selectors = [
            '[aria-label="Message body"]',
            'div[role="textbox"]',
            'div[contenteditable="true"]',
        ]
    elif provider in ("proton", "protonmail"):
        selectors = [
            '[data-testid="composer:body"] [contenteditable="true"]',
            'div[contenteditable="true"]',
        ]
    elif provider == "webde":
        selectors = [
            'div[contenteditable="true"]',
            '[aria-label*="Nachricht"]',
            'div[role="textbox"]',
        ]
    else:
        return False

    loc, _ = await _wait_for_any(page, selectors, timeout=5000)
    if loc:
        await loc.click()
        await _human_pause(0.3, 0.8)
        await loc.type(text, delay=random.randint(15, 40))
        return True
    return False


async def _click_send_button(page, provider: str) -> bool:
    """Click Send button in compose/reply view."""
    if provider in ("yahoo", "aol"):
        selectors = [
            'button[aria-label="Send this email"]',
            'button[title="Send this email"]',
            'button:has-text("Send")',
        ]
    elif provider == "gmail":
        selectors = [
            '[aria-label="Send"]',
            '[data-tooltip="Send"]',
            'div[role="button"]:has-text("Send")',
        ]
    elif provider in ("outlook", "hotmail"):
        selectors = [
            '[aria-label="Send"]',
            'button:has-text("Send")',
        ]
    elif provider in ("proton", "protonmail"):
        selectors = [
            '[data-testid="composer:send-button"]',
            'button:has-text("Send")',
        ]
    elif provider == "webde":
        selectors = [
            'button:has-text("Senden")',
            'button[aria-label*="Senden"]',
            'button[title*="Senden"]',
            'button:has-text("Send")',
        ]
    else:
        return False

    loc, _ = await _wait_for_any(page, selectors, timeout=5000)
    if loc:
        await loc.click()
        return True
    return False


async def _click_not_spam(page, provider: str) -> bool:
    """Click 'Not Spam' / 'Not Junk' button to rescue email from spam."""
    if provider in ("yahoo", "aol"):
        selectors = [
            'button[aria-label="Not spam"]',
            'button:has-text("Not Spam")',
            'button:has-text("Not spam")',
        ]
    elif provider == "gmail":
        selectors = [
            'button:has-text("Not spam")',
            '[aria-label="Not spam"]',
            'button:has-text("Report as not spam")',
        ]
    elif provider in ("outlook", "hotmail"):
        selectors = [
            'button:has-text("Not junk")',
            '[aria-label="Not junk"]',
            'button:has-text("It\'s not junk")',
        ]
    elif provider in ("proton", "protonmail"):
        selectors = [
            'button:has-text("Move to inbox")',
            '[data-testid="toolbar:moveto"]',
            'button:has-text("Not spam")',
        ]
    elif provider == "webde":
        selectors = [
            'button:has-text("Kein Spam")',
            'button:has-text("Nicht Spam")',
            'button:has-text("Not spam")',
            'button:has-text("In Posteingang")',
        ]
    else:
        return False

    loc, _ = await _wait_for_any(page, selectors, timeout=5000)
    if loc:
        await loc.click()
        return True
    return False
