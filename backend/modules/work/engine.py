"""
Leomail v3 - Work Module (Mass Mailing Engine)
Browser-based sending: open profile, compose with template variables + spintax, send, track.
Supports: Yahoo, AOL, Gmail, Outlook/Hotmail.
"""
import random
import asyncio
import json
from datetime import datetime
from loguru import logger
from sqlalchemy.orm import Session
from pathlib import Path

from ...database import SessionLocal
from ...models import (
    Account, Farm, Task, TaskStatus, ThreadLog,
    Link, RecipientDatabase, MailingStats,
)
from ..browser_manager import BrowserManager
from ...services.template_engine import render_template
from ...services.error_handler import error_handler
from ...config import load_config
from ..screenshot import debug_screenshot, register_page, unregister_page


# ─────────────────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────────────────
MAX_CONSECUTIVE_ERRORS = 3  # pause account after N errors in a row


def _load_recipients(db_record: RecipientDatabase) -> list[dict]:
    """
    Load recipients from a database file.
    Supports both JSON (new) and legacy CSV/TXT formats.
    """
    filepath = Path(db_record.file_path)
    if not filepath.exists():
        # Try relative path
        filepath = Path("user_data/databases") / db_record.file_path
    if not filepath.exists():
        logger.error(f"Recipient file not found: {db_record.file_path}")
        return []

    recipients = []

    # JSON format (new, saved by databases.py)
    if filepath.suffix == ".json":
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            for entry in data:
                email = entry.get("email", "").strip()
                if "@" in email:
                    recipients.append({
                        "email": email,
                        "first_name": entry.get("first_name", ""),
                        "last_name": entry.get("last_name", ""),
                    })
        except Exception as e:
            logger.error(f"JSON parse error: {e}")
        return recipients

    # Legacy TXT/CSV format (fallback)
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(",")
            email = parts[0].strip()
            if "@" not in email:
                continue

            first_name = parts[1].strip() if len(parts) >= 2 else ""
            last_name = parts[2].strip() if len(parts) >= 3 else ""
            recipients.append({
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            })

    return recipients


class LinkRotator:
    """
    Sequential link rotator with cycle tracking.

    Cycles through links in ORDER: 1->2->...->N->1->2->...->N
    max_uses: per-link usage limit (0 = unlimited)
    max_cycles: how many times to loop through the entire list (0 = unlimited)

    Presets:
      max_cycles=0, max_uses=0  -> unlimited cycling
      max_cycles=1, max_uses=1  -> single-use (each link exactly once)
      max_cycles=3, max_uses=0  -> 3 full passes through the list
    """

    def __init__(self, links: list, max_uses: int = 0, max_cycles: int = 0):
        self.links = links
        self.max_uses = max_uses      # per-link limit (0 = ∞)
        self.max_cycles = max_cycles  # list-level limit (0 = ∞)
        self.usage = {}               # url -> count
        self.index = 0
        self.current_cycle = 0
        self._exhausted = False

    def next(self) -> str | None:
        """Get next available link URL (strictly sequential)."""
        if not self.links or self._exhausted:
            return None

        # Try up to full list length to find an available link
        for _ in range(len(self.links)):
            # Check if we've completed a cycle
            if self.index >= len(self.links):
                self.index = 0
                self.current_cycle += 1
                if self.max_cycles > 0 and self.current_cycle >= self.max_cycles:
                    self._exhausted = True
                    return None  # all cycles done

            url = self.links[self.index]
            self.index += 1

            # Check per-link usage limit
            if self.max_uses > 0 and self.usage.get(url, 0) >= self.max_uses:
                continue

            return url

        # All links exhausted (all at max_uses)
        self._exhausted = True
        return None

    def record_use(self, link_url: str):
        """Record link usage."""
        self.usage[link_url] = self.usage.get(link_url, 0) + 1

    @property
    def total_available(self) -> int:
        """How many total link uses are available."""
        if not self.links:
            return 0
        if self.max_cycles == 0 and self.max_uses == 0:
            return 999999  # unlimited
        if self.max_cycles > 0 and self.max_uses == 0:
            return len(self.links) * self.max_cycles
        if self.max_cycles == 0 and self.max_uses > 0:
            return len(self.links) * self.max_uses
        return len(self.links) * min(self.max_cycles, self.max_uses)


# ─────────────────────────────────────────────────────────
#  HUMAN-LIKE HELPERS
# ─────────────────────────────────────────────────────────

async def _human_delay(lo: float = 0.3, hi: float = 1.0):
    await asyncio.sleep(random.uniform(lo, hi))


async def _type_human(page, selector: str, text: str, is_contenteditable: bool = False):
    """
    Type text into a field with human-like delays.
    For contenteditable divs (message body), uses JS to set text.
    """
    el = page.locator(selector).first
    await el.click()
    await _human_delay(0.3, 0.7)

    if is_contenteditable:
        # Use JS injection for contenteditable (handles Cyrillic, special chars)
        await page.evaluate(
            """(sel, txt) => {
                const el = document.querySelector(sel);
                if (el) {
                    el.focus();
                    el.textContent = txt;
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                }
            }""",
            selector, text,
        )
    else:
        # Clear then type char-by-char for regular inputs
        await el.fill("")
        await _human_delay(0.2, 0.4)
        # Use JS for non-ASCII text
        if any(ord(c) > 127 for c in text):
            await page.evaluate(
                """(sel, val) => {
                    const el = document.querySelector(sel);
                    if(el) {
                        el.focus();
                        const nativeSetter = Object.getOwnPropertyDescriptor(
                            window.HTMLInputElement.prototype, 'value'
                        ).set;
                        nativeSetter.call(el, val);
                        el.dispatchEvent(new Event('input', {bubbles: true}));
                        el.dispatchEvent(new Event('change', {bubbles: true}));
                    }
                }""",
                selector, text,
            )
        else:
            await el.type(text, delay=random.randint(30, 80))

    await _human_delay(0.3, 0.8)


# ─────────────────────────────────────────────────────────
#  WORK SESSION (per-account worker)
# ─────────────────────────────────────────────────────────

class WorkSession:
    """Single account sending worker."""

    def __init__(
        self,
        account: Account,
        browser_manager: BrowserManager,
        templates: list[tuple[str, str, str]],  # [(name, subject, body), ...]
        link_rotator: LinkRotator,
        delay_min: int,
        delay_max: int,
        emails_per_day_min: int,
        emails_per_day_max: int,
        thread_log: ThreadLog = None,
        task_id: int = None,
    ):
        self.account = account
        self.browser_manager = browser_manager
        self.templates = templates
        self.link_rotator = link_rotator
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.emails_per_day_min = emails_per_day_min
        self.emails_per_day_max = emails_per_day_max
        self.thread_log = thread_log
        self.task_id = task_id
        self.sent_count = 0
        self.error_count = 0
        self.bounce_count = 0
        self.consecutive_errors = 0

    async def run(self, recipients: list[dict], db: Session):
        """Execute sending for this account."""
        provider = self.account.provider or "yahoo"
        # User sets how many emails per day - no hardcoded limits
        emails_today = random.randint(self.emails_per_day_min, self.emails_per_day_max)
        emails_today = min(emails_today, len(recipients))

        if emails_today <= 0:
            logger.warning(f"Work [{self.account.email}]: no recipients")
            return {"sent": 0, "errors": 0, "bounces": 0}

        logger.info(f"Work [{self.account.email}]: sending {emails_today} emails via {provider}")

        # Load session
        context, session_path = await self.browser_manager.load_session_context(
            account_id=self.account.id,
            proxy=self.account.proxy,
            device_type="desktop",
            geo=self.account.geo,
        )

        thread_id = self.thread_log.id if self.thread_log else 0
        try:
            page = await context.new_page()
            register_page(thread_id, page, context, engine="work")

            # Navigate to mail provider
            mail_urls = {
                "yahoo": "https://mail.yahoo.com/",
                "aol": "https://mail.aol.com/",
                "gmail": "https://mail.google.com",
                "outlook": "https://outlook.live.com/mail",
                "hotmail": "https://outlook.live.com/mail",
            }
            mail_url = mail_urls.get(provider, "https://mail.yahoo.com/")
            await page.goto(mail_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(random.uniform(3, 6))

            # Close any welcome modals (Yahoo/AOL)
            if provider in ("yahoo", "aol"):
                await self._dismiss_modals(page)

            # Check session validity
            if "signin" in page.url or "login" in page.url:
                logger.warning(f"Work [{self.account.email}]: session expired")
                await debug_screenshot(page, "session_expired", self.account.email, "work")
                self._record_stat(db, "", "error", "Session expired")
                return {"sent": 0, "errors": 1, "bounces": 0}

            # Send to recipients
            batch = recipients[:emails_today]
            for i, recipient in enumerate(batch):
                if self.consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    logger.warning(
                        f"Work [{self.account.email}]: {MAX_CONSECUTIVE_ERRORS} "
                        f"consecutive errors - pausing account"
                    )
                    await debug_screenshot(page, "consecutive_errors_pause", self.account.email, "work")
                    self.account.status = "paused"
                    db.commit()
                    break

                # Pick random template
                tmpl_name, tmpl_subject, tmpl_body = random.choice(self.templates)

                # Get next link
                link_url = self.link_rotator.next() or ""

                # Render: substitute variables only (each letter already unique)
                subject, body = render_template(
                    tmpl_subject, tmpl_body,
                    recipient=recipient,
                    link_url=link_url,
                )

                # Update thread log
                if self.thread_log:
                    self.thread_log.current_action = (
                        f"Sending {i + 1}/{len(batch)} -> {recipient['email']}"
                    )
                    self.thread_log.updated_at = datetime.utcnow()
                    db.commit()

                try:
                    # Route to provider-specific sender
                    if provider in ("yahoo", "aol"):
                        await self._send_yahoo_aol(page, recipient["email"], subject, body, provider)
                    elif provider in ("outlook", "hotmail"):
                        await self._send_outlook(page, recipient["email"], subject, body)
                    elif provider == "gmail":
                        await self._send_gmail(page, recipient["email"], subject, body)

                    self.sent_count += 1
                    self.consecutive_errors = 0

                    # Record link usage
                    if link_url:
                        self.link_rotator.record_use(link_url)

                    # Record success stat
                    self._record_stat(db, recipient["email"], "sent", template_name=tmpl_name)

                    logger.debug(f"Work [{self.account.email}] -> {recipient['email']} ")

                except Exception as e:
                    error_msg = str(e)
                    self.error_count += 1
                    self.consecutive_errors += 1
                    logger.error(f"Work [{self.account.email}] -> {recipient['email']} : {error_msg}")

                    # Record error stat
                    self._record_stat(
                        db, recipient["email"], "error",
                        error_msg=error_msg, template_name=tmpl_name,
                    )
                    await debug_screenshot(page, "send_error", self.account.email, "work")

                    # Error handling
                    action = error_handler.handle_send_error(
                        email=self.account.email,
                        error=error_msg,
                        recipient=recipient["email"],
                    )

                    if action.get("action") == "stop":
                        logger.warning(f"Work [{self.account.email}]: stopping (error handler)")
                        break
                    elif action.get("action") == "skip":
                        continue

                # Random delay between emails (ALWAYS different)
                delay = random.uniform(self.delay_min, self.delay_max)
                delay += random.uniform(-5, 5)  # jitter
                delay = max(5, delay)
                logger.debug(f"Work [{self.account.email}]: delay {delay:.0f}s")
                await asyncio.sleep(delay)

            # Save session
            await self.browser_manager.save_session(context, self.account.id)

            # Update account stats
            self.account.total_emails_sent = (self.account.total_emails_sent or 0) + self.sent_count
            self.account.last_email_sent_at = datetime.utcnow()
            self.account.last_active = datetime.utcnow()
            if self.sent_count > 0:
                self.account.status = "sending"
            db.commit()

        except Exception as e:
            logger.error(f"Work [{self.account.email}] fatal: {e}")
            self.error_count += 1
            try:
                await debug_screenshot(page, "fatal_error", self.account.email, "work")
            except Exception:
                pass
        finally:
            unregister_page(thread_id)
            await self.browser_manager.close_context(context)

        return {
            "sent": self.sent_count,
            "errors": self.error_count,
            "bounces": self.bounce_count,
        }

    def _record_stat(
        self, db: Session, recipient: str, status: str,
        error_msg: str = None, template_name: str = None,
    ):
        """Record a MailingStats entry."""
        try:
            stat = MailingStats(
                task_id=self.task_id,
                account_email=self.account.email,
                recipient_email=recipient,
                template_name=template_name or "",
                status=status,
                error_message=error_msg,
                provider=self.account.provider,
            )
            db.add(stat)
            db.commit()
        except Exception as e:
            logger.error(f"Failed to record stat: {e}")

    # ───────────────────────────────────────────────────
    #  YAHOO / AOL SENDER
    # ───────────────────────────────────────────────────

    async def _dismiss_modals(self, page):
        """Close welcome/promo modals in Yahoo/AOL."""
        await asyncio.sleep(1)
        for selector in [
            'button:has-text("OK")',
            'button:has-text("Got it")',
            'button:has-text("Done")',
            'button:has-text("Continue")',
            'button:has-text("Skip")',
            'button[aria-label="Close"]',
            '[data-test-id="close-btn"]',
        ]:
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=500):
                    await el.click()
                    await _human_delay(0.5, 1)
            except Exception:
                pass

    async def _send_yahoo_aol(self, page, to_email: str, subject: str, body: str, provider: str = "yahoo"):
        """
        Compose and send email in Yahoo Mail or AOL Mail.
        Both use identical selectors (same platform).
        """
        # Click compose button
        if provider == "aol":
            compose_sel = 'a[data-test-id="compose-button"], button:has-text("Compose")'
        else:
            compose_sel = 'button[aria-label="New message"], a[data-test-id="compose-button"]'

        await page.locator(compose_sel).first.click(timeout=10000)
        await asyncio.sleep(random.uniform(1.5, 3))

        # Fill "To"
        to_field = page.locator('input#message-to-field')
        await to_field.click()
        await _human_delay(0.2, 0.5)
        await to_field.type(to_email, delay=random.randint(30, 70))
        await _human_delay(0.3, 0.6)
        await page.keyboard.press("Tab")
        await _human_delay(0.5, 1)

        # Fill "Subject" (may contain Cyrillic - use JS)
        await _type_human(page, 'input#compose-subject-input', subject)
        await _human_delay(0.3, 0.8)

        # Fill "Body" (contenteditable div - use JS for all text)
        await _type_human(
            page, 'div[aria-label="Message body"]',
            body, is_contenteditable=True,
        )
        await _human_delay(0.5, 1.5)

        # Click Send
        send_selectors = [
            'button[aria-label="Send this email"]',
            'button[title="Send this email"]',
            'button:has-text("Send")',
        ]
        for sel in send_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=1000):
                    await btn.click()
                    break
            except Exception:
                continue

        # Wait for confirmation
        await asyncio.sleep(random.uniform(2, 4))

        # Check for errors on page
        page_text = await page.inner_text("body")
        if "limit" in page_text.lower() or "too many" in page_text.lower():
            raise Exception("Daily sending limit detected")
        if "temporarily locked" in page_text.lower():
            raise Exception("Account temporarily locked")

    # ───────────────────────────────────────────────────
    #  GMAIL SENDER
    # ───────────────────────────────────────────────────

    async def _send_gmail(self, page, to_email: str, subject: str, body: str):
        """Compose and send in Gmail."""
        await page.click('[gh="cm"], [data-tooltip="Compose"]', timeout=10000)
        await asyncio.sleep(random.uniform(1, 2.5))

        await _type_human(page, 'input[name="to"], [aria-label="To recipients"]', to_email)
        await _human_delay(0.5, 1.5)

        await _type_human(page, 'input[name="subjectbox"]', subject)
        await _human_delay(0.3, 1)

        await _type_human(
            page, '[aria-label="Message Body"], [role="textbox"]',
            body, is_contenteditable=True,
        )
        await _human_delay(0.5, 2)

        await page.click('[aria-label="Send"], [data-tooltip="Send"]')
        await asyncio.sleep(random.uniform(2, 4))

    # ───────────────────────────────────────────────────
    #  OUTLOOK / HOTMAIL SENDER
    # ───────────────────────────────────────────────────

    async def _send_outlook(self, page, to_email: str, subject: str, body: str):
        """Compose and send in Outlook."""
        await page.click('[aria-label="New mail"], button:has-text("New mail")', timeout=10000)
        await asyncio.sleep(random.uniform(1, 3))

        await _type_human(page, '[aria-label="To"], input[role="combobox"]', to_email)
        await _human_delay(1, 2)
        await page.keyboard.press("Tab")

        await _type_human(page, '[aria-label="Add a subject"]', subject)
        await _human_delay(0.3, 1)

        await _type_human(
            page, '[aria-label="Message body"], [role="textbox"]',
            body, is_contenteditable=True,
        )
        await _human_delay(0.5, 2)

        await page.click('[aria-label="Send"], button:has-text("Send")')
        await asyncio.sleep(random.uniform(2, 4))


# ─────────────────────────────────────────────────────────
#  MAIN TASK RUNNER
# ─────────────────────────────────────────────────────────

async def run_work_task(
    farm_ids: list[int],
    database_ids: list[int],
    link_database_ids: list[int],
    template_ids: list[int],
    emails_per_day_min: int = 25,
    emails_per_day_max: int = 75,
    delay_min: int = 30,
    delay_max: int = 180,
    max_link_uses: int = 0,
    max_link_cycles: int = 0,
    same_provider: bool = False,
    threads: int = 10,
):
    """Run mass mailing campaign."""
    from ...models import Template, LinkDatabase

    db = SessionLocal()
    task = None
    try:
        # ─── PRE-FLIGHT: Load & validate all resources ───

        # 1. Accounts
        farms = db.query(Farm).filter(Farm.id.in_(farm_ids)).all()
        all_accounts = []
        for farm in farms:
            all_accounts.extend(farm.accounts)
        accounts = [a for a in all_accounts if a.status not in ("dead", "banned")]

        if not accounts:
            logger.error("Work: no eligible accounts")
            task = Task(type="work", status=TaskStatus.STOPPED, total_items=0,
                        stop_reason="Process stopped because - no available accounts in selected farms")
            db.add(task); db.commit()
            return

        # 2. Recipients
        all_recipients = []
        db_records_for_tracking = []  # track DB records to update used_count
        for db_id in database_ids:
            db_record = db.query(RecipientDatabase).get(db_id)
            if db_record:
                all_recipients.extend(_load_recipients(db_record))
                db_records_for_tracking.append(db_record)

        if not all_recipients:
            logger.error("Work: no recipients loaded")
            task = Task(type="work", status=TaskStatus.STOPPED, total_items=0,
                        stop_reason="Process stopped because - no recipients in selected databases (empty or not found)")
            db.add(task); db.commit()
            return

        # Filter out already-sent recipients (skip those already in MailingStats)
        sent_rows = db.query(MailingStats.recipient_email).filter(
            MailingStats.status == "sent"
        ).all()
        already_sent = {row[0] for row in sent_rows}
        before_filter = len(all_recipients)
        all_recipients = [r for r in all_recipients if r["email"] not in already_sent]
        skipped = before_filter - len(all_recipients)
        if skipped > 0:
            logger.info(f"Work: filtered {skipped} already-sent, {len(all_recipients)} remaining")

        if not all_recipients:
            logger.warning("Work: all recipients already sent")
            task = Task(type="work", status=TaskStatus.STOPPED, total_items=0,
                        stop_reason="Process stopped - all recipients already received emails (no resend needed)")
            db.add(task); db.commit()
            return

        # Shuffle recipients to avoid patterns
        random.shuffle(all_recipients)

        # 3. Links
        all_link_urls = []
        for ldb_id in link_database_ids:
            ldb = db.query(LinkDatabase).get(ldb_id)
            if ldb:
                from ...config import CONFIG_DIR
                fpath = CONFIG_DIR / ldb.file_path
                if not fpath.exists():
                    fpath = Path("user_data/links") / ldb.file_path
                if fpath.exists():
                    with open(fpath, "r", encoding="utf-8") as f:
                        lines = [l.strip() for l in f if l.strip().startswith("http")]
                        all_link_urls.extend(lines)

        # If link packs were selected but no links loaded - stop
        if link_database_ids and not all_link_urls:
            logger.error("Work: link packs selected but no links loaded")
            task = Task(type="work", status=TaskStatus.STOPPED, total_items=0,
                        stop_reason="Process stopped because - link packs selected but links not loaded (files empty or not found)")
            db.add(task); db.commit()
            return

        link_rotator = LinkRotator(all_link_urls, max_uses=max_link_uses, max_cycles=max_link_cycles)

        # 4. Templates
        templates = db.query(Template).filter(Template.id.in_(template_ids)).all()
        template_triples = [(t.name, t.subject, t.body) for t in templates]

        if not template_triples:
            logger.error("Work: no templates")
            task = Task(type="work", status=TaskStatus.STOPPED, total_items=0,
                        stop_reason="Process stopped - no templates for mailing")
            db.add(task); db.commit()
            return

        logger.info(
            f"Work: {len(accounts)} accounts, {len(all_recipients)} recipients, "
            f"{len(all_link_urls)} links, {len(template_triples)} templates, {threads} threads"
        )

        # ─── CREATE TASK ───
        task = Task(
            type="work",
            status=TaskStatus.RUNNING,
            total_items=len(all_recipients),
            thread_count=threads,
            details=f"Sending {len(all_recipients)} recipients via {len(accounts)} accounts",
        )
        db.add(task)
        db.commit()

        # Shared flag: set when a critical resource is exhausted mid-process
        links_exhausted = [False]
        exhaustion_reason = [None]

        # Distribute recipients across accounts with cross/same provider filtering
        def _get_provider(email: str) -> str:
            """Extract provider from recipient email domain."""
            domain = email.split("@")[-1].lower()
            if "gmail" in domain or "googlemail" in domain:
                return "gmail"
            elif "yahoo" in domain:
                return "yahoo"
            elif "aol" in domain:
                return "aol"
            elif "hotmail" in domain:
                return "hotmail"
            elif "outlook" in domain or "live.com" in domain or "msn" in domain:
                return "outlook"
            return "other"

        per_account = max(1, len(all_recipients) // len(accounts))
        account_batches = []
        for i, account in enumerate(accounts):
            start = i * per_account
            end = start + per_account if i < len(accounts) - 1 else len(all_recipients)
            batch = all_recipients[start:end]
            if batch:
                # Cross/Same provider filtering per-account
                acc_provider = (account.provider or "").lower()
                if same_provider and acc_provider:
                    # SAME: only send to recipients whose domain matches account provider
                    batch = [r for r in batch if _get_provider(r['email']) == acc_provider]
                elif not same_provider and acc_provider:
                    # CROSS: only send to recipients with DIFFERENT provider
                    batch = [r for r in batch if _get_provider(r['email']) != acc_provider]
                if batch:
                    account_batches.append((account, batch))

        if not account_batches:
            task.status = TaskStatus.STOPPED
            task.stop_reason = "Process stopped - no data for account distribution"
            task.completed_at = datetime.utcnow()
            db.commit()
            return

        # Start browser engine
        browser_manager = BrowserManager(headless=False)
        await browser_manager.start()

        try:
            semaphore = asyncio.Semaphore(threads)

            async def process_account(account, recipients_batch):
                async with semaphore:
                    # Check if another thread already detected resource exhaustion
                    if links_exhausted[0]:
                        return

                    thread_log = ThreadLog(
                        task_id=task.id,
                        thread_type="work",
                        status="running",
                        account_email=account.email,
                    )
                    db.add(thread_log)
                    db.commit()

                    session = WorkSession(
                        account=account,
                        browser_manager=browser_manager,
                        templates=template_triples,
                        link_rotator=link_rotator,
                        delay_min=delay_min,
                        delay_max=delay_max,
                        emails_per_day_min=emails_per_day_min,
                        emails_per_day_max=emails_per_day_max,
                        thread_log=thread_log,
                        task_id=task.id,
                    )

                    result = await session.run(recipients_batch, db)

                    thread_log.status = "done"
                    thread_log.current_action = (
                        f"Done: {result['sent']} sent, {result['errors']} errors"
                    )
                    task.completed_items = (task.completed_items or 0) + result["sent"]
                    task.failed_items = (task.failed_items or 0) + result["errors"]

                    # Update used_count on recipient databases
                    if result["sent"] > 0:
                        per_db = max(1, result["sent"] // max(1, len(db_records_for_tracking)))
                        for db_rec in db_records_for_tracking:
                            db_rec.used_count = (db_rec.used_count or 0) + per_db

                    db.commit()

                    # Check if links exhausted after this session
                    if link_database_ids and link_rotator.next() is None and max_link_uses > 0:
                        links_exhausted[0] = True
                        exhaustion_reason[0] = "Thread завершился потому что - ссылки for писем закончились (все использованы до лимита)"
                        logger.warning(f"Work [{account.email}]: links exhausted - signaling stop")

            # Launch all account workers with staggered start
            async_tasks = []
            for account, batch in account_batches:
                if links_exhausted[0]:
                    break
                jitter = random.uniform(0, 30)
                await asyncio.sleep(jitter)
                async_tasks.append(asyncio.create_task(process_account(account, batch)))

            await asyncio.gather(*async_tasks, return_exceptions=True)

            # Determine final status
            if exhaustion_reason[0]:
                task.status = TaskStatus.STOPPED
                task.stop_reason = exhaustion_reason[0]
                logger.warning(f"Work task stopped: {exhaustion_reason[0]}")
            else:
                task.status = TaskStatus.COMPLETED
                task.stop_reason = None

            task.completed_at = datetime.utcnow()
            db.commit()

        finally:
            await browser_manager.stop()

    except Exception as e:
        logger.error(f"Work task failed: {e}")
        if task and task.id:
            try:
                task.status = TaskStatus.FAILED
                task.stop_reason = f"Process stopped - critical error: {str(e)[:200]}"
                task.completed_at = datetime.utcnow()
                db.commit()
            except Exception:
                pass
    finally:
        db.close()
