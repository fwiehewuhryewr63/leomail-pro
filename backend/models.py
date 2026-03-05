from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Boolean, Float, Text, Table
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from .database import Base


# === ENUMS ===

class AccountStatus(str, enum.Enum):
    NEW = "new"
    PHASE_1 = "phase_1"   # Day 1-3:   1-3 emails/day
    PHASE_2 = "phase_2"   # Day 4-7:   5-10 emails/day
    PHASE_3 = "phase_3"   # Day 8-14:  10-20 emails/day
    PHASE_4 = "phase_4"   # Day 15-21: 20-50 emails/day
    PHASE_5 = "phase_5"   # Day 22-30: 50-100 emails/day
    WARMED = "warmed"      # Fully warmed - ready for mass mailing
    SENDING = "sending"
    PAUSED = "paused"
    DEAD = "dead"
    BANNED = "banned"


class ProxyStatus(str, enum.Enum):
    ACTIVE = "active"
    BOUND = "bound"          # hard-bound to an account (1:1), not available for new births
    EXPIRED = "expired"
    BANNED = "banned"
    DEAD = "dead"
    EXHAUSTED = "exhausted"  # all provider limits hit, user should delete from proxy service

class ProxyType(str, enum.Enum):
    SOCKS5 = "socks5"
    HTTP = "http"          # datacenter HTTP
    HTTPS = "https"        # residential HTTPS
    MOBILE = "mobile"
    RESIDENTIAL = "residential"  # residential socks5/https

class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    STOPPED = "stopped"    # Resource exhaustion / graceful stop with reason
    FAILED = "failed"

class ThreadType(str, enum.Enum):
    BIRTH = "birth"
    WARMUP = "warmup"
    WORK = "work"
    VALIDATOR = "validator"

class Gender(str, enum.Enum):
    MALE = "male"
    FEMALE = "female"
    RANDOM = "random"


# === Association table for Farm <-> Account ===
farm_accounts = Table(
    "farm_accounts", Base.metadata,
    Column("farm_id", Integer, ForeignKey("farms.id"), primary_key=True),
    Column("account_id", Integer, ForeignKey("accounts.id"), primary_key=True)
)


# === MODELS ===

class Proxy(Base):
    __tablename__ = "proxies"

    id = Column(Integer, primary_key=True, index=True)
    host = Column(String, nullable=False)
    port = Column(Integer, nullable=False)
    username = Column(String, nullable=True)
    password = Column(String, nullable=True)
    protocol = Column(String, default="http")  # http, socks5 (auto-derived from proxy_type)
    proxy_type = Column(String, default="http")  # socks5, http, mobile
    status = Column(String, default=ProxyStatus.ACTIVE)
    geo = Column(String, nullable=True)  # US, DE, etc.
    
    # Monitoring
    last_check = Column(DateTime, nullable=True)
    response_time_ms = Column(Integer, nullable=True)
    fail_count = Column(Integer, default=0)
    external_ip = Column(String, nullable=True)  # Detected external IP from check
    
    # Binding & usage tracking
    bound_account_id = Column(Integer, nullable=True)  # 1:1 with account (birth IP)
    use_count = Column(Integer, default=0)  # total usage across all providers
    total_births = Column(Integer, default=0)  # lifetime successful births
    total_fails = Column(Integer, default=0)   # lifetime failed births
    
    # Per-provider usage counters (legacy, kept for compatibility)
    use_gmail = Column(Integer, default=0)
    use_yahoo = Column(Integer, default=0)
    use_aol = Column(Integer, default=0)
    use_outlook = Column(Integer, default=0)
    use_hotmail = Column(Integer, default=0)
    use_protonmail = Column(Integer, default=0)
    use_tuta = Column(Integer, default=0)  # DEPRECATED: Tuta provider removed, kept for DB schema compat
    
    source = Column(String, default="manual")  # manual, asocks, proxycheap
    external_id = Column(String, nullable=True)  # ID from proxy provider for dedup
    
    # ASN classification (cached from ip-api.com — survives restarts)
    asn = Column(String, nullable=True)        # e.g. "AS49981"
    asn_type = Column(String, nullable=True)    # datacenter, residential, mobile, unknown
    
    expires_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)  # cooldown: when proxy was last used for birth
    created_at = Column(DateTime, default=datetime.utcnow)

    accounts = relationship("Account", back_populates="proxy")

    @property
    def effective_protocol(self):
        """Derive connection protocol from proxy_type."""
        pt = (self.proxy_type or "http").lower()
        if pt == "socks5":
            return "socks5"
        return "http"   # http, https, mobile, residential all use HTTP protocol for Playwright

    def to_string(self):
        proto = self.effective_protocol
        if self.username and self.password:
            return f"{proto}://{self.username}:{self.password}@{self.host}:{self.port}"
        return f"{proto}://{self.host}:{self.port}"

    def to_playwright(self):
        """Return dict for Playwright proxy config."""
        proto = self.effective_protocol
        config = {"server": f"{proto}://{self.host}:{self.port}"}
        # Chromium does NOT support socks5 proxy authentication
        if self.username and proto != "socks5":
            config["username"] = self.username
            config["password"] = self.password or ""
        return config


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    password = Column(String, nullable=False)
    recovery_email = Column(String, nullable=True)
    recovery_phone = Column(String, nullable=True)

    provider = Column(String, index=True)  # gmail, outlook, yahoo, aol, hotmail
    status = Column(String, default=AccountStatus.NEW)

    # Identity (birth data)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    gender = Column(String, nullable=True)  # male, female
    birthday = Column(DateTime, nullable=True)
    geo = Column(String, nullable=True)  # US, DE, BR...
    language = Column(String, default="en")

    # Birth fingerprint
    birth_ip = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    browser_profile_path = Column(String, nullable=True)  # path to saved profile

    # Warmup tracking
    warmup_day = Column(Integer, default=0)  # day of warmup (0 = not started)
    warmup_started_at = Column(DateTime, nullable=True)
    emails_sent_today = Column(Integer, default=0)
    total_emails_sent = Column(Integer, default=0)
    last_email_sent_at = Column(DateTime, nullable=True)
    bounces = Column(Integer, default=0)

    # Health
    health_score = Column(Float, default=100.0)  # 0-100
    imap_verified = Column(Boolean, default=False)  # IMAP login check after birth
    imap_checked_at = Column(DateTime, nullable=True)

    # Proxy binding
    proxy_id = Column(Integer, ForeignKey("proxies.id"), nullable=True)
    proxy = relationship("Proxy", back_populates="accounts")

    # Metadata: cookies, fingerprint, etc.
    metadata_blob = Column(JSON, default={})

    # Farms (many-to-many)
    farms = relationship("Farm", secondary=farm_accounts, back_populates="accounts")

    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, nullable=True)

    def to_export(self):
        """Export account to portable JSON format."""
        return {
            "email": self.email,
            "password": self.password,
            "provider": self.provider,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "gender": self.gender,
            "birthday": self.birthday.isoformat() if self.birthday else None,
            "geo": self.geo,
            "language": self.language,
            "birth_ip": self.birth_ip,
            "user_agent": self.user_agent,
            "warmup_day": self.warmup_day,
            "status": self.status,
            "health_score": self.health_score,
            "cookies": self.metadata_blob.get("cookies", []) if self.metadata_blob else [],
            "fingerprint": self.metadata_blob.get("fingerprint", {}) if self.metadata_blob else {},
        }


class Farm(Base):
    __tablename__ = "farms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)

    accounts = relationship("Account", secondary=farm_accounts, back_populates="farms")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Template(Base):
    __tablename__ = "templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    subject = Column(String, nullable=False)  # may contain {{LINK}}, {{FIRSTNAME}}, etc.
    body = Column(Text, nullable=False)  # HTML, may contain {{LINK}}, {{FIRSTNAME}}, {{LASTNAME}}, {{EMAILNAME}}
    content_type = Column(String, default="html")  # html, plain
    language = Column(String, default="en")
    pack_name = Column(String, nullable=True)  # name of import pack (ZIP)
    niche = Column(String, nullable=True)       # nutra / dating / casino / crypto / general
    variables = Column(JSON, default=[])  # detected variables: ["LINK", "FIRSTNAME", ...]

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RecipientDatabase(Base):
    __tablename__ = "recipient_databases"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)  # relative to user_data/databases/
    total_count = Column(Integer, default=0)
    used_count = Column(Integer, default=0)
    invalid_count = Column(Integer, default=0)
    with_name = Column(Boolean, default=False)  # True = email,FirstName,LastName format

    created_at = Column(DateTime, default=datetime.utcnow)


class LinkDatabase(Base):
    """File-based link packs (similar to recipient databases)."""
    __tablename__ = "link_databases"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)  # e.g. "Crypto Offers 2024"
    file_path = Column(String, nullable=False)  # relative to user_data/links/
    total_count = Column(Integer, default=0)
    niche = Column(String, nullable=True)       # nutra / dating / casino / crypto / general
    
    created_at = Column(DateTime, default=datetime.utcnow)


class NamePack(Base):
    """Uploadable name packs for registration (firstname,lastname per line)."""
    __tablename__ = "name_packs"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    total_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class Link(Base):
    """DEPRECATED (v3.1): Not used. Kept for DB schema compatibility. Use CampaignLink instead."""
    __tablename__ = "links"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    click_count = Column(Integer, default=0)
    use_count = Column(Integer, default=0)
    active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String, index=True)  # birth, warmup, work, validator
    status = Column(String, default=TaskStatus.PENDING)
    details = Column(String, nullable=True)
    stop_reason = Column(String, nullable=True)  # Why the task stopped/terminated

    # Progress
    total_items = Column(Integer, default=0)
    completed_items = Column(Integer, default=0)
    failed_items = Column(Integer, default=0)

    # Thread tracking
    thread_count = Column(Integer, default=1)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    @property
    def progress_pct(self):
        if self.total_items == 0:
            return 0
        return int((self.completed_items / self.total_items) * 100)


class ThreadLog(Base):
    """Per-thread activity log for live monitoring."""
    __tablename__ = "thread_logs"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    thread_index = Column(Integer, default=0)
    thread_type = Column(String)  # birth, warmup, work
    status = Column(String, default="idle")  # idle, running, paused, error, done
    current_action = Column(String, nullable=True)  # "filling name...", "solving captcha..."
    account_email = Column(String, nullable=True)
    proxy_info = Column(String, nullable=True)
    error_message = Column(String, nullable=True)
    screenshot_path = Column(String, nullable=True)

    started_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class NameDatabase(Base):
    """Uploaded name lists for Birth module. Each file: FirstName,LastName per line."""
    __tablename__ = "name_databases"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)  # display name, e.g. "US Male Names"
    file_path = Column(String, nullable=False)  # relative to user_data/names/
    country = Column(String, default="any")  # ISO: us, de, ru, any
    gender = Column(String, default="any")  # male, female, any
    total_count = Column(Integer, default=0)  # number of name pairs in file

    created_at = Column(DateTime, default=datetime.utcnow)


class MailingStats(Base):
    """Per-email send tracking for statistics and error reporting."""
    __tablename__ = "mailing_stats"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    account_email = Column(String, index=True)
    recipient_email = Column(String, index=True)
    template_name = Column(String, nullable=True)
    status = Column(String, index=True)  # "sent", "error", "bounce", "limit"
    error_message = Column(String, nullable=True)
    provider = Column(String, nullable=True)  # yahoo, aol, gmail, outlook

    sent_at = Column(DateTime, default=datetime.utcnow)


class WarmupEmail(Base):
    """Cross-farm warmup email tracking: who sent to whom, delivery status, replies."""
    __tablename__ = "warmup_emails"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    sender_account_id = Column(Integer, ForeignKey("accounts.id"), index=True)
    receiver_account_id = Column(Integer, ForeignKey("accounts.id"), index=True)
    subject = Column(String, nullable=True)
    sent_at = Column(DateTime, default=datetime.utcnow)

    # Delivery tracking (filled by receiver pass)
    delivery_status = Column(String, default="pending")  # pending | inbox | spam | not_found
    checked_at = Column(DateTime, nullable=True)

    # Reply tracking
    replied = Column(Boolean, default=False)
    replied_at = Column(DateTime, nullable=True)


# ─── CAMPAIGN / BLITZ PIPELINE (v4) ──────────────────────────────────────────

class CampaignStatus(str, enum.Enum):
    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    STOPPED = "stopped"      # Resource exhaustion / manual stop


class Campaign(Base):
    """Blitz Pipeline campaign - continuous Birth -> Send -> Die -> Repeat."""
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)              # "Brazil Nutra"
    geo = Column(String, nullable=False)               # "BR"
    niche = Column(String, default="general")          # nutra / dating / casino

    status = Column(String, default=CampaignStatus.DRAFT)
    stop_reason = Column(String, nullable=True)        # why it stopped

    # Birth config
    name_pack = Column(String, default="brazil_5k")    # name pack filename (without .txt)
    providers = Column(JSON, default=list)              # ["gmail", "yahoo"]
    gender = Column(String, default="female")           # always female for burn model

    # Thread allocation
    birth_threads = Column(Integer, default=10)
    send_threads = Column(Integer, default=20)

    # Link embedding
    link_mode = Column(String, default="hyperlink")    # hyperlink / raw

    # Send settings (migrated from Work)
    emails_per_day_min = Column(Integer, default=25)
    emails_per_day_max = Column(Integer, default=75)
    delay_min = Column(Integer, default=30)            # seconds between sends
    delay_max = Column(Integer, default=180)
    same_provider = Column(Boolean, default=False)     # True = same, False = cross
    max_link_uses = Column(Integer, default=0)         # 0 = unlimited
    max_link_cycles = Column(Integer, default=0)       # 0 = unlimited

    # Account source
    use_existing = Column(Boolean, default=False)      # True = use existing farm accounts
    farm_ids = Column(JSON, default=list)              # farm IDs when use_existing=True

    # Live stats (updated by engine)
    total_sent = Column(Integer, default=0)
    total_errors = Column(Integer, default=0)
    accounts_born = Column(Integer, default=0)
    accounts_dead = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    templates = relationship("CampaignTemplate", back_populates="campaign", cascade="all, delete-orphan")
    links = relationship("CampaignLink", back_populates="campaign", cascade="all, delete-orphan")
    recipients = relationship("CampaignRecipient", back_populates="campaign", cascade="all, delete-orphan")

    @property
    def progress_pct(self):
        total = len(self.recipients) if self.recipients else 0
        if total == 0:
            return 0
        sent = sum(1 for r in self.recipients if r.sent)
        return int((sent / total) * 100)


class CampaignTemplate(Base):
    """Email template for a campaign - rotated randomly during send."""
    __tablename__ = "campaign_templates"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    subject = Column(String, nullable=False)            # may contain {first_name}, {link}
    body_html = Column(Text, nullable=False)            # HTML with {first_name}, {link}, {date}
    style = Column(String, nullable=True)               # fomo / professional / casual
    use_count = Column(Integer, default=0)
    active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    campaign = relationship("Campaign", back_populates="templates")


class CampaignLink(Base):
    """ESP tracking link for a campaign - rotated with use limits + #hash randomization."""
    __tablename__ = "campaign_links"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    esp_url = Column(String, nullable=False)            # ESP tracking URL
    use_count = Column(Integer, default=0)
    max_uses = Column(Integer, default=100)             # per-link limit before burning
    active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    campaign = relationship("Campaign", back_populates="links")


class CampaignRecipient(Base):
    """Target email for a campaign - tracks sent status per recipient."""
    __tablename__ = "campaign_recipients"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    email = Column(String, nullable=False)
    first_name = Column(String, nullable=True)             # VIP: name from database
    sent = Column(Boolean, default=False, index=True)
    sent_at = Column(DateTime, nullable=True)
    result = Column(String, nullable=True)              # ok / bounce / error

    campaign = relationship("Campaign", back_populates="recipients")
