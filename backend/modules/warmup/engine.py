"""
Leomail v3 — Cross-Farm Warmup Engine
Sender farms send emails → Receiver farms check inbox + reply.
5-phase auto-warmup with progressive email limits.
"""
import random
import asyncio
from datetime import datetime
from loguru import logger

from ...database import SessionLocal
from ...models import (
    Account, Farm, Template, Task, TaskStatus, ThreadLog,
    AccountStatus, WarmupEmail,
)
from ..browser.manager import BrowserManager
from ..template_engine import render_template
from ..screenshot import debug_screenshot, register_page, unregister_page

# Phase definitions: phase_num -> (day_from, day_to, emails_min, emails_max, status)
PHASES = {
    1: (1,  3,   1,   3,  AccountStatus.PHASE_1),
    2: (4,  7,   5,  10,  AccountStatus.PHASE_2),
    3: (8,  14, 10,  20,  AccountStatus.PHASE_3),
    4: (15, 21, 20,  50,  AccountStatus.PHASE_4),
    5: (22, 30, 50, 100,  AccountStatus.PHASE_5),
}


def get_phase_for_day(warmup_day: int):
    """Return phase number (1-5) for given warmup day. Returns 0 if day > 30 (warmed)."""
    for phase, (d_from, d_to, *_) in PHASES.items():
        if d_from <= warmup_day <= d_to:
            return phase
    return 0  # fully warmed


def get_phase_limits(warmup_day: int):
    """Return (emails_min, emails_max) for the current warmup day."""
    for phase, (d_from, d_to, e_min, e_max, _) in PHASES.items():
        if d_from <= warmup_day <= d_to:
            return (e_min, e_max)
    return (50, 100)  # warmed accounts: max rate


def get_phase_status(warmup_day: int):
    """Return the AccountStatus for the given warmup day."""
    for phase, (d_from, d_to, _, _, status) in PHASES.items():
        if d_from <= warmup_day <= d_to:
            return status
    return AccountStatus.WARMED


class WarmupSession:
    """Single account warmup worker."""

    def __init__(
        self,
        account: Account,
        targets: list[Account],  # receiver accounts to send TO
        browser_manager: BrowserManager,
        template_subject: str,
        template_body: str,
        delay_min: int,
        delay_max: int,
        emails_per_day_min: int,
        emails_per_day_max: int,
        phase_override: int = 0,
        same_provider: bool = False,
        thread_log: ThreadLog = None,
    ):
        self.account = account
        self.targets = targets
        self.browser_manager = browser_manager
        self.template_subject = template_subject
        self.template_body = template_body
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.emails_per_day_min = emails_per_day_min
        self.emails_per_day_max = emails_per_day_max
        self.phase_override = phase_override
        self.same_provider = same_provider
        self.thread_log = thread_log
        self.sent_count = 0
        self.error_count = 0
        self.sent_emails = []  # List of (sender_id, receiver_id, subject) for tracking

    async def run(self, db, task_id: int = None):
        """Execute warmup for this account: sends to receiver farm accounts."""
        # Compute phase limits
        if self.phase_override > 0:
            # Force specific phase
            phase = self.phase_override
            if phase in PHASES:
                _, _, phase_min, phase_max, _ = PHASES[phase]
            else:
                phase_min, phase_max = 1, 5
        else:
            # Auto: use account's warmup day
            current_day = (self.account.warmup_day or 0) + 1
            phase = get_phase_for_day(current_day)
            phase_min, phase_max = get_phase_limits(current_day)

        emails_today = random.randint(phase_min, phase_max)
        current_day = (self.account.warmup_day or 0) + 1

        logger.info(f"Warmup [{self.account.email}]: day {current_day}, phase {phase}, "
                     f"sending {emails_today} emails (range {phase_min}-{phase_max})")

        # Filter targets by provider rule
        available_targets = list(self.targets)
        if self.same_provider:
            my_provider = self.account.provider
            available_targets = [t for t in available_targets if t.provider == my_provider]

        if not available_targets:
            logger.warning(f"Warmup [{self.account.email}]: no targets available")
            return {"sent": 0, "errors": 0}

        # Load browser session
        context, session_path = await self.browser_manager.load_session_context(
            account_id=self.account.id,
            proxy=self.account.proxy,
            device_type="desktop",
            geo=self.account.geo,
        )

        thread_id = self.thread_log.id if self.thread_log else 0
        try:
            page = await context.new_page()
            provider = self.account.provider or "gmail"
            register_page(thread_id, page, context, engine="warmup")

            # Navigate to mail
            mail_urls = {
                "gmail": "https://mail.google.com",
                "outlook": "https://outlook.live.com/mail",
                "hotmail": "https://outlook.live.com/mail",
                "yahoo": "https://mail.yahoo.com",
                "aol": "https://mail.aol.com",
            }
            mail_url = mail_urls.get(provider, "https://mail.google.com")
            await page.goto(mail_url, wait_until="domcontentloaded", timeout=30000)

            # Check if logged in
            await asyncio.sleep(random.uniform(2, 5))
            await debug_screenshot(page, "mail_opened", self.account.email, "warmup")
            current_url = page.url

            if "signin" in current_url or "login" in current_url or "accounts.google.com" in current_url:
                logger.info(f"Warmup [{self.account.email}]: session expired, re-login needed")
                await debug_screenshot(page, "session_expired", self.account.email, "warmup")
                await self._relogin(page, provider)

            # Send emails to receiver farm accounts
            for i in range(emails_today):
                target = random.choice(available_targets)

                recipient = {
                    "email": target.email,
                    "first_name": target.first_name or "",
                    "last_name": target.last_name or "",
                }
                subject, body = render_template(
                    self.template_subject, self.template_body,
                    recipient=recipient, unique=True,
                )

                if self.thread_log:
                    self._update_log(db, f"Sending email {i + 1}/{emails_today} to {target.email}")

                try:
                    if provider == "gmail":
                        await self._send_gmail(page, target.email, subject, body)
                    elif provider in ("outlook", "hotmail"):
                        await self._send_outlook(page, target.email, subject, body)
                    elif provider == "yahoo":
                        await self._send_yahoo(page, target.email, subject, body)
                    elif provider == "aol":
                        await self._send_aol(page, target.email, subject, body)

                    self.sent_count += 1
                    self.sent_emails.append((self.account.id, target.id, subject))

                    # Track in WarmupEmail table
                    warmup_email = WarmupEmail(
                        task_id=task_id,
                        sender_account_id=self.account.id,
                        receiver_account_id=target.id,
                        subject=subject,
                        delivery_status="pending",
                    )
                    db.add(warmup_email)
                    db.commit()

                    logger.debug(f"Warmup [{self.account.email}] → {target.email} ✓")

                except Exception as e:
                    self.error_count += 1
                    logger.error(f"Warmup [{self.account.email}] send error: {e}")
                    await debug_screenshot(page, "send_error", self.account.email, "warmup")

                # Random delay
                delay = random.uniform(self.delay_min, self.delay_max)
                delay += random.uniform(-5, 5)
                delay = max(5, delay)
                await asyncio.sleep(delay)

            # Read some inbox emails (human behavior)
            try:
                await self._read_inbox(page, provider)
            except Exception:
                pass

            # Save session
            await self.browser_manager.save_session(context, self.account.id)

            # Update account stats
            self.account.emails_sent_today = self.sent_count
            self.account.total_emails_sent = (self.account.total_emails_sent or 0) + self.sent_count
            self.account.last_email_sent_at = datetime.utcnow()
            self.account.warmup_day = current_day
            self.account.last_active = datetime.utcnow()

            # Advance warmup phase status
            if self.phase_override > 0:
                # Force phase status
                _, _, _, _, forced_status = PHASES.get(self.phase_override, (0, 0, 0, 0, AccountStatus.PHASE_1))
                self.account.status = forced_status
            else:
                new_status = get_phase_status(current_day)
                old_status = self.account.status
                if old_status != new_status:
                    logger.info(f"Warmup [{self.account.email}]: {old_status} → {new_status}")
                    self.account.status = new_status

            db.commit()

        except Exception as e:
            logger.error(f"Warmup [{self.account.email}] fatal: {e}")
            self.error_count += 1
            try:
                await debug_screenshot(page, "fatal_error", self.account.email, "warmup")
            except Exception:
                pass
        finally:
            unregister_page(thread_id)
            await self.browser_manager.close_context(context)

        return {"sent": self.sent_count, "errors": self.error_count}

    async def _send_gmail(self, page, to_email: str, subject: str, body: str):
        """Compose and send email in Gmail."""
        await page.click('[gh="cm"]')  # Compose button
        await asyncio.sleep(random.uniform(1, 2))
        await page.fill('input[name="to"]', to_email)
        await asyncio.sleep(random.uniform(0.5, 1))
        await page.fill('input[name="subjectbox"]', subject)
        await asyncio.sleep(random.uniform(0.5, 1))

        body_div = page.locator('div[aria-label="Message Body"]')
        await body_div.click()
        await body_div.type(body, delay=random.randint(20, 60))
        await asyncio.sleep(random.uniform(0.5, 1.5))

        await page.click('[aria-label="Send"]')
        await asyncio.sleep(random.uniform(2, 4))

    async def _send_outlook(self, page, to_email: str, subject: str, body: str):
        """Compose and send email in Outlook."""
        await page.click('button[aria-label="New mail"]')
        await asyncio.sleep(random.uniform(1.5, 3))
        await page.fill('input[aria-label="To"]', to_email)
        await asyncio.sleep(random.uniform(0.5, 1))
        await page.press('input[aria-label="To"]', 'Tab')
        await asyncio.sleep(0.5)
        await page.fill('input[aria-label="Add a subject"]', subject)
        await asyncio.sleep(random.uniform(0.5, 1))

        body_div = page.locator('div[aria-label="Message body"]')
        await body_div.click()
        await body_div.type(body, delay=random.randint(20, 60))
        await asyncio.sleep(random.uniform(0.5, 1.5))

        await page.click('button[aria-label="Send"]')
        await asyncio.sleep(random.uniform(2, 4))

    async def _send_yahoo(self, page, to_email: str, subject: str, body: str):
        """Compose and send email in Yahoo Mail."""
        compose_btn = page.locator('a[data-test-id="compose-button"]')
        if await compose_btn.count() == 0:
            compose_btn = page.locator('a[aria-label="Compose"]')
        await compose_btn.click()
        await asyncio.sleep(random.uniform(1.5, 3))
        await page.fill('input#message-to-field', to_email)
        await asyncio.sleep(random.uniform(0.5, 1))
        await page.press('input#message-to-field', 'Enter')
        await asyncio.sleep(0.5)
        await page.fill('input[data-test-id="compose-subject"]', subject)
        await asyncio.sleep(random.uniform(0.5, 1))
        body_div = page.locator('div[data-test-id="compose-editor-container"] div[role="textbox"]')
        await body_div.click()
        await body_div.type(body, delay=random.randint(20, 60))
        await asyncio.sleep(random.uniform(0.5, 1.5))
        send_btn = page.locator('button[data-test-id="compose-send-button"]')
        await send_btn.click()
        await asyncio.sleep(random.uniform(2, 4))

    async def _send_aol(self, page, to_email: str, subject: str, body: str):
        """Compose and send email in AOL Mail (same UI as Yahoo)."""
        compose_btn = page.locator('a[data-test-id="compose-button"]')
        if await compose_btn.count() == 0:
            compose_btn = page.locator('a[aria-label="Compose"]')
        await compose_btn.click()
        await asyncio.sleep(random.uniform(1.5, 3))
        await page.fill('input#message-to-field', to_email)
        await asyncio.sleep(random.uniform(0.5, 1))
        await page.press('input#message-to-field', 'Enter')
        await asyncio.sleep(0.5)
        await page.fill('input[data-test-id="compose-subject"]', subject)
        await asyncio.sleep(random.uniform(0.5, 1))
        body_div = page.locator('div[data-test-id="compose-editor-container"] div[role="textbox"]')
        await body_div.click()
        await body_div.type(body, delay=random.randint(20, 60))
        await asyncio.sleep(random.uniform(0.5, 1.5))
        send_btn = page.locator('button[data-test-id="compose-send-button"]')
        await send_btn.click()
        await asyncio.sleep(random.uniform(2, 4))

    async def _read_inbox(self, page, provider: str):
        """Read a few emails to simulate human behavior."""
        try:
            if provider == "gmail":
                emails = page.locator('tr[role="row"]')
            elif provider in ("outlook", "hotmail"):
                emails = page.locator('div[role="option"]')
            elif provider in ("yahoo", "aol"):
                emails = page.locator('a[data-test-id="message-list-item"]')
            else:
                return
            count = await emails.count()
            read_count = min(random.randint(1, 3), count)
            for i in range(read_count):
                await emails.nth(i).click()
                await asyncio.sleep(random.uniform(2, 5))
        except Exception:
            pass

    async def _relogin(self, page, provider: str):
        """Attempt re-login (placeholder — needs provider-specific flow)."""
        logger.warning(f"Warmup [{self.account.email}]: re-login not implemented yet")

    def _update_log(self, db, action: str):
        self.thread_log.current_action = action
        self.thread_log.updated_at = datetime.utcnow()
        db.commit()


class ReceiverSession:
    """Receiver account: check inbox for warmup emails, detect inbox/spam, reply."""

    def __init__(self, account: Account, browser_manager: BrowserManager,
                 expected_senders: list[str], thread_log: ThreadLog = None):
        self.account = account
        self.browser_manager = browser_manager
        self.expected_senders = expected_senders  # email addresses to look for
        self.thread_log = thread_log
        self.checked_count = 0
        self.inbox_count = 0
        self.spam_count = 0
        self.replied_count = 0

    async def run(self, db, task_id: int = None):
        """Check inbox/spam for emails from senders, reply to them."""
        logger.info(f"Receiver [{self.account.email}]: checking for {len(self.expected_senders)} senders")

        context, _ = await self.browser_manager.load_session_context(
            account_id=self.account.id,
            proxy=self.account.proxy,
            device_type="desktop",
            geo=self.account.geo,
        )

        thread_id = self.thread_log.id if self.thread_log else 0
        try:
            page = await context.new_page()
            provider = self.account.provider or "gmail"
            register_page(thread_id, page, context, engine="warmup_rx")

            mail_urls = {
                "gmail": "https://mail.google.com",
                "outlook": "https://outlook.live.com/mail",
                "hotmail": "https://outlook.live.com/mail",
                "yahoo": "https://mail.yahoo.com",
                "aol": "https://mail.aol.com",
            }
            mail_url = mail_urls.get(provider, "https://mail.google.com")
            await page.goto(mail_url, wait_until="domcontentloaded", timeout=30000)

            await asyncio.sleep(random.uniform(3, 6))
            await debug_screenshot(page, "receiver_inbox", self.account.email, "warmup")

            # Check if logged in
            current_url = page.url
            if "signin" in current_url or "login" in current_url:
                logger.warning(f"Receiver [{self.account.email}]: session expired")
                await debug_screenshot(page, "receiver_session_expired", self.account.email, "warmup")
                await self.browser_manager.save_session(context, self.account.id)
                return {"checked": 0, "inbox": 0, "spam": 0, "replied": 0}

            # Check inbox for expected sender emails
            pending_emails = db.query(WarmupEmail).filter(
                WarmupEmail.receiver_account_id == self.account.id,
                WarmupEmail.task_id == task_id,
                WarmupEmail.delivery_status == "pending",
            ).all()

            for warmup_email in pending_emails:
                sender = db.query(Account).filter(Account.id == warmup_email.sender_account_id).first()
                if not sender:
                    continue

                if self.thread_log:
                    self.thread_log.current_action = f"Checking for email from {sender.email}"
                    db.commit()

                # Search in inbox
                found_location = await self._search_for_email(page, provider, sender.email, warmup_email.subject)

                warmup_email.checked_at = datetime.utcnow()

                if found_location == "inbox":
                    warmup_email.delivery_status = "inbox"
                    self.inbox_count += 1
                    logger.debug(f"Receiver [{self.account.email}]: {sender.email} → INBOX ✓")
                    await debug_screenshot(page, "delivery_inbox", self.account.email, "warmup")

                    # Reply to the email
                    try:
                        replied = await self._reply_to_email(page, provider)
                        if replied:
                            warmup_email.replied = True
                            warmup_email.replied_at = datetime.utcnow()
                            self.replied_count += 1
                            logger.debug(f"Receiver [{self.account.email}]: replied to {sender.email} ✓")
                    except Exception as e:
                        logger.error(f"Receiver [{self.account.email}]: reply error: {e}")

                elif found_location == "spam":
                    warmup_email.delivery_status = "spam"
                    self.spam_count += 1
                    logger.warning(f"Receiver [{self.account.email}]: {sender.email} → SPAM ⚠")
                    await debug_screenshot(page, "delivery_spam", self.account.email, "warmup")

                    # Move from spam to inbox (helps reputation)
                    try:
                        await self._move_from_spam(page, provider)
                    except Exception:
                        pass

                else:
                    warmup_email.delivery_status = "not_found"
                    logger.debug(f"Receiver [{self.account.email}]: {sender.email} → NOT FOUND")

                self.checked_count += 1
                db.commit()

                await asyncio.sleep(random.uniform(2, 5))

            # Read a few other emails for naturalness
            try:
                await self._read_random_emails(page, provider)
            except Exception:
                pass

            # Save session
            await self.browser_manager.save_session(context, self.account.id)

            # Update account activity
            self.account.last_active = datetime.utcnow()
            db.commit()

        except Exception as e:
            logger.error(f"Receiver [{self.account.email}] fatal: {e}")
            try:
                await debug_screenshot(page, "receiver_fatal", self.account.email, "warmup")
            except Exception:
                pass
        finally:
            unregister_page(thread_id)
            await self.browser_manager.close_context(context)

        return {
            "checked": self.checked_count,
            "inbox": self.inbox_count,
            "spam": self.spam_count,
            "replied": self.replied_count,
        }

    async def _search_for_email(self, page, provider: str, sender_email: str, subject: str) -> str:
        """Search inbox and spam for email from sender. Returns 'inbox', 'spam', or 'not_found'."""
        try:
            if provider == "gmail":
                # Search inbox
                search_box = page.locator('input[aria-label="Search mail"]')
                await search_box.click()
                await search_box.fill(f"from:{sender_email}")
                await page.keyboard.press("Enter")
                await asyncio.sleep(random.uniform(2, 4))

                # Check if results found
                results = page.locator('tr.zA')
                count = await results.count()
                if count > 0:
                    await results.first.click()
                    await asyncio.sleep(random.uniform(1, 3))
                    return "inbox"

                # Check spam
                await search_box.click()
                await search_box.fill(f"in:spam from:{sender_email}")
                await page.keyboard.press("Enter")
                await asyncio.sleep(random.uniform(2, 4))

                spam_results = page.locator('tr.zA')
                if await spam_results.count() > 0:
                    await spam_results.first.click()
                    await asyncio.sleep(random.uniform(1, 3))
                    return "spam"

            elif provider in ("outlook", "hotmail"):
                # Search in Outlook
                search_box = page.locator('input[aria-label="Search"]')
                await search_box.click()
                await search_box.fill(f"from:{sender_email}")
                await page.keyboard.press("Enter")
                await asyncio.sleep(random.uniform(2, 4))

                results = page.locator('div[role="option"]')
                count = await results.count()
                if count > 0:
                    await results.first.click()
                    await asyncio.sleep(random.uniform(1, 3))
                    return "inbox"

                # Check junk
                try:
                    junk = page.locator('span:has-text("Junk Email")')
                    await junk.click()
                    await asyncio.sleep(random.uniform(1, 3))
                    junk_results = page.locator('div[role="option"]')
                    if await junk_results.count() > 0:
                        return "spam"
                except Exception:
                    pass

            elif provider in ("yahoo", "aol"):
                # Search in Yahoo/AOL
                search_box = page.locator('input#mail-search-input, input[aria-label="Search"]')
                await search_box.click()
                await search_box.fill(f"from:{sender_email}")
                await page.keyboard.press("Enter")
                await asyncio.sleep(random.uniform(2, 4))

                results = page.locator('a[data-test-id="message-list-item"]')
                count = await results.count()
                if count > 0:
                    await results.first.click()
                    await asyncio.sleep(random.uniform(1, 3))
                    return "inbox"

                # Check spam folder
                try:
                    spam_folder = page.locator('a[data-test-folder-name="Bulk"], a[data-test-folder-name="Spam"]')
                    if await spam_folder.count() > 0:
                        await spam_folder.first.click()
                        await asyncio.sleep(random.uniform(2, 4))
                        spam_results = page.locator('a[data-test-id="message-list-item"]')
                        if await spam_results.count() > 0:
                            await spam_results.first.click()
                            await asyncio.sleep(random.uniform(1, 3))
                            return "spam"
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Search error: {e}")

        return "not_found"

    async def _reply_to_email(self, page, provider: str) -> bool:
        """Reply to the currently open email with a short message."""
        try:
            reply_texts = [
                "Thanks!", "Got it, thanks!", "Received, thank you!",
                "Perfect, thanks for the update!", "Great, noted!",
                "Thank you for your email!", "Acknowledged, thanks!",
                "Appreciate it!", "Thanks for letting me know!",
            ]
            reply_text = random.choice(reply_texts)

            if provider == "gmail":
                reply_btn = page.locator('[aria-label="Reply"]')
                await reply_btn.click()
                await asyncio.sleep(random.uniform(1, 2))

                body_div = page.locator('div[aria-label="Message Body"]')
                await body_div.click()
                await body_div.type(reply_text, delay=random.randint(30, 80))
                await asyncio.sleep(random.uniform(0.5, 1.5))

                await page.click('[aria-label="Send"]')
                await asyncio.sleep(random.uniform(2, 4))
                return True

            elif provider in ("outlook", "hotmail"):
                reply_btn = page.locator('button[aria-label="Reply"]')
                await reply_btn.click()
                await asyncio.sleep(random.uniform(1, 2))

                body_div = page.locator('div[aria-label="Message body"]')
                await body_div.click()
                await body_div.type(reply_text, delay=random.randint(30, 80))
                await asyncio.sleep(random.uniform(0.5, 1.5))

                await page.click('button[aria-label="Send"]')
                await asyncio.sleep(random.uniform(2, 4))
                return True

            elif provider in ("yahoo", "aol"):
                reply_btn = page.locator('button[data-test-id="reply-button"], button[title="Reply"]')
                await reply_btn.click()
                await asyncio.sleep(random.uniform(1, 2))

                body_div = page.locator('div[data-test-id="compose-editor-container"] div[role="textbox"]')
                await body_div.click()
                await body_div.type(reply_text, delay=random.randint(30, 80))
                await asyncio.sleep(random.uniform(0.5, 1.5))

                send_btn = page.locator('button[data-test-id="compose-send-button"]')
                await send_btn.click()
                await asyncio.sleep(random.uniform(2, 4))
                return True

        except Exception as e:
            logger.error(f"Reply failed: {e}")
        return False

    async def _move_from_spam(self, page, provider: str):
        """Move email from spam to inbox (improves sender reputation)."""
        try:
            if provider == "gmail":
                not_spam_btn = page.locator('button:has-text("Not spam")')
                if await not_spam_btn.count() > 0:
                    await not_spam_btn.click()
                    await asyncio.sleep(1)
            elif provider in ("outlook", "hotmail"):
                not_junk_btn = page.locator('button:has-text("Not junk")')
                if await not_junk_btn.count() > 0:
                    await not_junk_btn.click()
                    await asyncio.sleep(1)
            elif provider in ("yahoo", "aol"):
                not_spam_btn = page.locator('button[data-test-id="toolbar-not-spam"], button:has-text("Not Spam")')
                if await not_spam_btn.count() > 0:
                    await not_spam_btn.first.click()
                    await asyncio.sleep(1)
        except Exception:
            pass

    async def _read_random_emails(self, page, provider: str):
        """Read a few random emails for natural behavior."""
        try:
            if provider == "gmail":
                # Go back to inbox
                await page.click('a[aria-label="Inbox"]')
                await asyncio.sleep(random.uniform(1, 3))
            elif provider in ("outlook", "hotmail"):
                await page.click('span:has-text("Inbox")')
                await asyncio.sleep(random.uniform(1, 3))
            elif provider in ("yahoo", "aol"):
                inbox_link = page.locator('a[data-test-folder-name="Inbox"]')
                if await inbox_link.count() > 0:
                    await inbox_link.click()
                    await asyncio.sleep(random.uniform(1, 3))

            if provider == "gmail":
                emails = page.locator('tr[role="row"]')
            elif provider in ("outlook", "hotmail"):
                emails = page.locator('div[role="option"]')
            elif provider in ("yahoo", "aol"):
                emails = page.locator('a[data-test-id="message-list-item"]')
            else:
                return
            count = await emails.count()
            read_count = min(random.randint(1, 3), count)
            for i in range(read_count):
                await emails.nth(i).click()
                await asyncio.sleep(random.uniform(2, 5))
        except Exception:
            pass


async def run_warmup_task(
    sender_farm_ids: list[int],
    receiver_farm_ids: list[int],
    template_ids: list[int],
    phase_override: int = 0,
    emails_per_day_min: int = 1,
    emails_per_day_max: int = 5,
    delay_min: int = 60,
    delay_max: int = 300,
    same_provider: bool = False,
    threads: int = 5,
):
    """
    Cross-farm warmup:
    1. Sender accounts send emails to receiver accounts
    2. Receiver accounts check inbox (inbox/spam detection)
    3. Receiver accounts reply to received emails
    """
    db = SessionLocal()
    task = None
    try:
        # ─── PRE-FLIGHT CHECKS ───

        # Get sender accounts
        sender_farms = db.query(Farm).filter(Farm.id.in_(sender_farm_ids)).all()
        sender_accounts = []
        for farm in sender_farms:
            sender_accounts.extend(farm.accounts)
        sender_accounts = [a for a in sender_accounts if a.status not in ("dead", "banned")]

        # Get receiver accounts (targets)
        receiver_farms = db.query(Farm).filter(Farm.id.in_(receiver_farm_ids)).all()
        receiver_accounts = []
        for farm in receiver_farms:
            receiver_accounts.extend(farm.accounts)
        receiver_accounts = [a for a in receiver_accounts if a.status not in ("dead", "banned")]

        if not sender_accounts:
            logger.error("Warmup: no sender accounts in selected farms")
            task = Task(type="warmup", status=TaskStatus.STOPPED, total_items=0,
                        stop_reason="Процесс завершился потому что — нет доступных аккаунтов-отправителей в выбранных фермах")
            db.add(task); db.commit()
            return
        if not receiver_accounts:
            logger.error("Warmup: no receiver accounts in selected farms")
            task = Task(type="warmup", status=TaskStatus.STOPPED, total_items=0,
                        stop_reason="Процесс завершился потому что — нет доступных аккаунтов-получателей в выбранных фермах")
            db.add(task); db.commit()
            return

        # Load templates
        templates = db.query(Template).filter(Template.id.in_(template_ids)).all()
        template_pairs = [(t.subject, t.body) for t in templates]
        if not template_pairs:
            logger.error("Warmup: no templates found")
            task = Task(type="warmup", status=TaskStatus.STOPPED, total_items=0,
                        stop_reason="Процесс завершился потому что — нет шаблонов для прогрева")
            db.add(task); db.commit()
            return

        logger.info(
            f"Warmup: {len(sender_accounts)} senders → {len(receiver_accounts)} receivers, "
            f"{len(template_pairs)} templates, phase={'auto' if phase_override == 0 else phase_override}, "
            f"{threads} threads"
        )

        # Create task record
        task = Task(
            type="warmup",
            status=TaskStatus.RUNNING,
            total_items=len(sender_accounts) + len(receiver_accounts),
            thread_count=threads,
            details=(
                f"Прогрев: {len(sender_accounts)} отправителей → {len(receiver_accounts)} получателей, "
                f"фаза {'авто' if phase_override == 0 else phase_override}"
            ),
        )
        db.add(task)
        db.commit()

        browser_manager = BrowserManager(headless=False)
        await browser_manager.start()

        try:
            # ===== PHASE 1: SENDER PASS =====
            logger.info(f"[Warmup] === SENDER PASS: {len(sender_accounts)} accounts ===")
            semaphore = asyncio.Semaphore(threads)

            async def process_sender(account):
                async with semaphore:
                    thread_log = ThreadLog(
                        task_id=task.id, thread_type="warmup", status="running",
                        account_email=account.email,
                    )
                    db.add(thread_log)
                    db.commit()

                    subj, body = random.choice(template_pairs)

                    session = WarmupSession(
                        account=account,
                        targets=receiver_accounts,
                        browser_manager=browser_manager,
                        template_subject=subj,
                        template_body=body,
                        delay_min=delay_min,
                        delay_max=delay_max,
                        emails_per_day_min=emails_per_day_min,
                        emails_per_day_max=emails_per_day_max,
                        phase_override=phase_override,
                        same_provider=same_provider,
                        thread_log=thread_log,
                    )

                    result = await session.run(db, task_id=task.id)

                    thread_log.status = "done"
                    thread_log.current_action = f"Sent {result['sent']}, errors {result['errors']}"
                    task.completed_items = (task.completed_items or 0) + 1
                    db.commit()

            # Send with jitter
            sender_tasks = []
            for account in sender_accounts:
                jitter = random.uniform(0, 30)
                await asyncio.sleep(jitter)
                sender_tasks.append(asyncio.create_task(process_sender(account)))

            await asyncio.gather(*sender_tasks, return_exceptions=True)
            logger.info(f"[Warmup] === SENDER PASS COMPLETE ===")

            # ===== PHASE 2: RECEIVER PASS =====
            # Wait a bit for emails to arrive
            wait_time = random.uniform(30, 90)
            logger.info(f"[Warmup] Waiting {wait_time:.0f}s for emails to arrive...")
            await asyncio.sleep(wait_time)

            logger.info(f"[Warmup] === RECEIVER PASS: {len(receiver_accounts)} accounts ===")
            sender_emails = [a.email for a in sender_accounts]

            async def process_receiver(account):
                async with semaphore:
                    thread_log = ThreadLog(
                        task_id=task.id, thread_type="warmup", status="running",
                        account_email=account.email,
                    )
                    db.add(thread_log)
                    db.commit()

                    session = ReceiverSession(
                        account=account,
                        browser_manager=browser_manager,
                        expected_senders=sender_emails,
                        thread_log=thread_log,
                    )

                    result = await session.run(db, task_id=task.id)

                    thread_log.status = "done"
                    thread_log.current_action = (
                        f"Checked {result['checked']}: "
                        f"{result['inbox']} inbox, {result['spam']} spam, "
                        f"{result['replied']} replied"
                    )
                    task.completed_items = (task.completed_items or 0) + 1
                    db.commit()

            receiver_tasks = []
            for account in receiver_accounts:
                jitter = random.uniform(0, 30)
                await asyncio.sleep(jitter)
                receiver_tasks.append(asyncio.create_task(process_receiver(account)))

            await asyncio.gather(*receiver_tasks, return_exceptions=True)
            logger.info(f"[Warmup] === RECEIVER PASS COMPLETE ===")

            # Mark task completed
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.utcnow()

            # Log final stats
            total_emails = db.query(WarmupEmail).filter(WarmupEmail.task_id == task.id).count()
            inbox_count = db.query(WarmupEmail).filter(
                WarmupEmail.task_id == task.id, WarmupEmail.delivery_status == "inbox"
            ).count()
            spam_count = db.query(WarmupEmail).filter(
                WarmupEmail.task_id == task.id, WarmupEmail.delivery_status == "spam"
            ).count()
            replied_count = db.query(WarmupEmail).filter(
                WarmupEmail.task_id == task.id, WarmupEmail.replied == True
            ).count()

            task.details = (
                f"Готово: {total_emails} отправлено, "
                f"{inbox_count} inbox ({inbox_count/total_emails*100:.0f}%), "
                f"{spam_count} spam, {replied_count} ответов"
            ) if total_emails > 0 else "Завершено"

            db.commit()
            logger.info(f"[Warmup] ✅ Complete: {total_emails} sent, {inbox_count} inbox, {spam_count} spam, {replied_count} replied")

        finally:
            await browser_manager.stop()

    except Exception as e:
        logger.error(f"Warmup task failed: {e}")
        if task and task.id:
            try:
                task.status = TaskStatus.FAILED
                task.stop_reason = f"Процесс завершился потому что — критическая ошибка: {str(e)[:200]}"
                task.completed_at = datetime.utcnow()
                db.commit()
            except Exception:
                pass
    finally:
        db.close()
