"""
Leomail v2.2 - Error Handler & Ban Controller
Full classification of SMTP errors, bans, limits, MailerDaemon, bounces.
Auto-actions: mark dead, pause, rotate, invalidate recipient.
"""
import re
from datetime import datetime
from loguru import logger


class ErrorType:
    BAN = "ban"
    LIMIT = "limit"
    MAILER_DAEMON = "mailer_daemon"
    SMTP_ERROR = "smtp_error"
    TIMEOUT = "timeout"
    CAPTCHA_FAIL = "captcha_fail"
    AUTH_FAIL = "auth_fail"
    INVALID_RECIPIENT = "invalid_recipient"
    BLACKLISTED = "blacklisted"
    UNKNOWN = "unknown"


# Patterns for classifying SMTP responses and errors
BAN_PATTERNS = [
    r"account.*(disabled|suspended|locked|blocked)",
    r"too many login attempts",
    r"access.*denied",
    r"temporarily.*deactivated",
    r"your account has been",
    r"policy violation",
]

LIMIT_PATTERNS = [
    r"rate limit",
    r"too many (messages|connections|recipients)",
    r"daily.*limit.*exceeded",
    r"exceeded.*quota",
    r"try again later",
    r"4\.7\.1",
    r"421.*too many",
    r"452.*too many",
]

MAILER_DAEMON_PATTERNS = [
    r"mailer.daemon",
    r"mail delivery.*failed",
    r"undelivered mail",
    r"delivery status notification",
    r"returned mail",
    r"delivery failure",
]

INVALID_RECIPIENT_PATTERNS = [
    r"user.*not found",
    r"mailbox.*not found",
    r"unknown.*user",
    r"no such user",
    r"recipient.*rejected",
    r"invalid.*recipient",
    r"does not exist",
    r"550.*5\.1\.1",
    r"553.*mailbox",
]

BLACKLIST_PATTERNS = [
    r"blacklist",
    r"blocklist",
    r"spamhaus",
    r"barracuda",
    r"listed.*rbl",
    r"rejected.*spam",
    r"5\.7\.1.*rejected",
]


class SendError:
    """Represents a classified sending error."""
    def __init__(self, error_type: str, raw_message: str, account_email: str = "",
                 recipient_email: str = "", action: str = ""):
        self.error_type = error_type
        self.raw_message = raw_message
        self.account_email = account_email
        self.recipient_email = recipient_email
        self.action = action
        self.timestamp = datetime.now()

    def to_dict(self):
        return {
            "type": self.error_type,
            "message": self.raw_message[:200],
            "account": self.account_email,
            "recipient": self.recipient_email,
            "action": self.action,
            "time": self.timestamp.isoformat(),
        }


class ErrorHandler:
    """Classifies errors and decides auto-actions."""

    def __init__(self):
        self.errors: list[SendError] = []
        self.account_bounces: dict[str, int] = {}  # email -> bounce count
        self.account_sent: dict[str, int] = {}      # email -> sent count
        self.domain_bounces: dict[str, int] = {}     # domain -> bounce count

    def classify(self, raw_error: str) -> str:
        """Classify raw error string into ErrorType."""
        lower = raw_error.lower()

        for pattern in BAN_PATTERNS:
            if re.search(pattern, lower):
                return ErrorType.BAN

        for pattern in BLACKLIST_PATTERNS:
            if re.search(pattern, lower):
                return ErrorType.BLACKLISTED

        for pattern in LIMIT_PATTERNS:
            if re.search(pattern, lower):
                return ErrorType.LIMIT

        for pattern in MAILER_DAEMON_PATTERNS:
            if re.search(pattern, lower):
                return ErrorType.MAILER_DAEMON

        for pattern in INVALID_RECIPIENT_PATTERNS:
            if re.search(pattern, lower):
                return ErrorType.INVALID_RECIPIENT

        if "timeout" in lower or "timed out" in lower:
            return ErrorType.TIMEOUT

        if "captcha" in lower:
            return ErrorType.CAPTCHA_FAIL

        if "authentication" in lower or "login" in lower or "credentials" in lower:
            return ErrorType.AUTH_FAIL

        return ErrorType.UNKNOWN

    def decide_action(self, error_type: str, account_email: str = "") -> str:
        """Decide what action to take based on error type."""
        actions = {
            ErrorType.BAN: "mark_dead",
            ErrorType.AUTH_FAIL: "mark_dead",
            ErrorType.BLACKLISTED: "mark_dead",
            ErrorType.LIMIT: "pause_1h",
            ErrorType.MAILER_DAEMON: "warning_only",  # yellow - account continues, just stat
            ErrorType.INVALID_RECIPIENT: "mark_recipient_invalid",
            ErrorType.TIMEOUT: "retry_later",
            ErrorType.CAPTCHA_FAIL: "retry_new_captcha",
            ErrorType.SMTP_ERROR: "retry_later",
            ErrorType.UNKNOWN: "log_warning",
        }
        action = actions.get(error_type, "log_warning")

        # Check bounce rate - only pause if extremely high (>10% over 20+ sends)
        if account_email and account_email in self.account_sent:
            sent = self.account_sent[account_email]
            bounces = self.account_bounces.get(account_email, 0)
            if sent > 20 and bounces / sent > 0.10:
                action = "pause_high_bounce"
                logger.warning(f"Account {account_email} bounce rate {bounces}/{sent} = {bounces/sent*100:.1f}% - pausing")

        return action

    def handle_error(self, raw_error: str, account_email: str = "", recipient_email: str = "") -> SendError:
        """Full pipeline: classify -> decide action -> record."""
        error_type = self.classify(raw_error)
        action = self.decide_action(error_type, account_email)

        error = SendError(error_type, raw_error, account_email, recipient_email, action)
        self.errors.append(error)

        # Track bounces
        if error_type in (ErrorType.MAILER_DAEMON, ErrorType.INVALID_RECIPIENT):
            self.account_bounces[account_email] = self.account_bounces.get(account_email, 0) + 1
            if recipient_email:
                domain = recipient_email.split("@")[-1] if "@" in recipient_email else ""
                if domain:
                    self.domain_bounces[domain] = self.domain_bounces.get(domain, 0) + 1

        logger.info(f"Error [{error_type}] account={account_email} -> action={action}")
        return error

    def record_sent(self, account_email: str):
        """Record a successful send for bounce rate calculation."""
        self.account_sent[account_email] = self.account_sent.get(account_email, 0) + 1

    def get_bounce_rate(self, account_email: str) -> float:
        """Get bounce rate for an account (0.0 - 1.0)."""
        sent = self.account_sent.get(account_email, 0)
        if sent == 0:
            return 0.0
        bounces = self.account_bounces.get(account_email, 0)
        return bounces / sent

    def get_stats(self) -> dict:
        """Error statistics for dashboard."""
        by_type = {}
        for e in self.errors:
            by_type[e.error_type] = by_type.get(e.error_type, 0) + 1

        # Top bouncing domains
        top_domains = sorted(self.domain_bounces.items(), key=lambda x: -x[1])[:10]

        # Accounts with high bounce rate
        risky_accounts = []
        for email, sent in self.account_sent.items():
            if sent > 5:
                rate = self.get_bounce_rate(email)
                if rate > 0.03:
                    risky_accounts.append({"email": email, "sent": sent, "bounces": self.account_bounces.get(email, 0), "rate": round(rate * 100, 1)})

        return {
            "total_errors": len(self.errors),
            "by_type": by_type,
            "top_bounce_domains": [{"domain": d, "bounces": c} for d, c in top_domains],
            "risky_accounts": sorted(risky_accounts, key=lambda x: -x["rate"]),
            "recent": [e.to_dict() for e in self.errors[-20:]],
        }


# Singleton
error_handler = ErrorHandler()
