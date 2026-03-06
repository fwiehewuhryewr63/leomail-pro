"""
Leomail v4 - Alert Monitor
Threshold-based system health alerts — polled by Dashboard.
Checks: bounce rates, account deaths, proxy pool, SMS availability,
warmup health, and resource depletion.
"""
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
from loguru import logger


class AlertLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Alert:
    level: str
    category: str
    title: str
    message: str
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self):
        return {
            "level": self.level,
            "category": self.category,
            "title": self.title,
            "message": self.message,
            "timestamp": self.timestamp,
        }


class AlertMonitor:
    """
    Threshold-based system health monitor.
    Call check_all(db) to get a list of current alerts.
    """

    # ── Thresholds (configurable) ──
    BOUNCE_RATE_WARN = 0.05       # 5% bounce rate warning
    BOUNCE_RATE_CRIT = 0.10       # 10% critical
    BOUNCE_MIN_SENDS = 20         # minimum sends before checking rate
    DEATH_SPIKE_COUNT = 3         # deaths in 1 hour = spike
    PROXY_LOW_WARN = 10           # less than 10 proxies available
    PROXY_LOW_CRIT = 3            # less than 3 = critical
    WARMUP_HEALTH_WARN = 70       # avg health score warning
    WARMUP_HEALTH_CRIT = 50       # avg health critical

    def check_all(self, db) -> list[Alert]:
        """Run all threshold checks and return active alerts."""
        alerts = []
        alerts.extend(self._check_bounce_rates(db))
        alerts.extend(self._check_death_spike(db))
        alerts.extend(self._check_proxy_pool(db))
        alerts.extend(self._check_warmup_health(db))
        alerts.extend(self._check_sms_services())
        alerts.extend(self._check_error_handler())
        return alerts

    def _check_bounce_rates(self, db) -> list[Alert]:
        """Check if any account has dangerously high bounce rate."""
        alerts = []
        try:
            from ..services.error_handler import error_handler
            for email, sent in error_handler.account_sent.items():
                if sent < self.BOUNCE_MIN_SENDS:
                    continue
                rate = error_handler.get_bounce_rate(email)
                if rate >= self.BOUNCE_RATE_CRIT:
                    alerts.append(Alert(
                        level=AlertLevel.CRITICAL,
                        category="bounce_rate",
                        title="Critical bounce rate",
                        message=f"{email}: {rate*100:.1f}% bounce rate ({sent} sends)",
                    ))
                elif rate >= self.BOUNCE_RATE_WARN:
                    alerts.append(Alert(
                        level=AlertLevel.WARNING,
                        category="bounce_rate",
                        title="High bounce rate",
                        message=f"{email}: {rate*100:.1f}% bounce rate ({sent} sends)",
                    ))
        except Exception as e:
            logger.debug(f"[AlertMonitor] bounce check failed: {e}")
        return alerts

    def _check_death_spike(self, db) -> list[Alert]:
        """Check if too many accounts died recently (ban wave?)."""
        alerts = []
        try:
            from ..models import Account
            one_hour_ago = datetime.utcnow() - timedelta(hours=1)
            recent_deaths = db.query(Account).filter(
                Account.status.in_(["dead", "banned"]),
                Account.last_active >= one_hour_ago,
            ).count()
            if recent_deaths >= self.DEATH_SPIKE_COUNT:
                alerts.append(Alert(
                    level=AlertLevel.CRITICAL,
                    category="death_spike",
                    title="Account death spike",
                    message=f"{recent_deaths} accounts died in the last hour — possible ban wave",
                ))
        except Exception as e:
            logger.debug(f"[AlertMonitor] death spike check failed: {e}")
        return alerts

    def _check_proxy_pool(self, db) -> list[Alert]:
        """Check proxy availability."""
        alerts = []
        try:
            from ..models import Proxy
            active = db.query(Proxy).filter(Proxy.status == "active").count()
            if active <= self.PROXY_LOW_CRIT:
                alerts.append(Alert(
                    level=AlertLevel.CRITICAL,
                    category="proxy_pool",
                    title="Proxy pool critical",
                    message=f"Only {active} active proxies remaining",
                ))
            elif active <= self.PROXY_LOW_WARN:
                alerts.append(Alert(
                    level=AlertLevel.WARNING,
                    category="proxy_pool",
                    title="Proxy pool low",
                    message=f"Only {active} active proxies remaining",
                ))
        except Exception as e:
            logger.debug(f"[AlertMonitor] proxy check failed: {e}")
        return alerts

    def _check_warmup_health(self, db) -> list[Alert]:
        """Check average health score of warming accounts."""
        alerts = []
        try:
            from sqlalchemy import func
            from ..models import Account, AccountStatus
            warming_statuses = [
                AccountStatus.PHASE_1, AccountStatus.PHASE_2,
                AccountStatus.PHASE_3, AccountStatus.PHASE_4, AccountStatus.PHASE_5,
            ]
            avg_health = db.query(func.avg(Account.health_score)).filter(
                Account.status.in_(warming_statuses),
            ).scalar()

            if avg_health is not None:
                avg_health = round(avg_health, 1)
                if avg_health < self.WARMUP_HEALTH_CRIT:
                    alerts.append(Alert(
                        level=AlertLevel.CRITICAL,
                        category="warmup_health",
                        title="Warmup health critical",
                        message=f"Average health score: {avg_health}/100 — accounts may be failing",
                    ))
                elif avg_health < self.WARMUP_HEALTH_WARN:
                    alerts.append(Alert(
                        level=AlertLevel.WARNING,
                        category="warmup_health",
                        title="Warmup health declining",
                        message=f"Average health score: {avg_health}/100",
                    ))
        except Exception as e:
            logger.debug(f"[AlertMonitor] warmup health check failed: {e}")
        return alerts

    def _check_sms_services(self) -> list[Alert]:
        """Check SMS provider availability."""
        alerts = []
        try:
            from ..modules.birth._helpers import _sms_backoff
            for service, info in _sms_backoff.items():
                fails = info.get("fails", 0)
                if fails >= 5:
                    alerts.append(Alert(
                        level=AlertLevel.CRITICAL,
                        category="sms_degraded",
                        title=f"SMS service degraded: {service}",
                        message=f"{fails} consecutive failures — service may be down",
                    ))
                elif fails >= 3:
                    alerts.append(Alert(
                        level=AlertLevel.WARNING,
                        category="sms_degraded",
                        title=f"SMS service issues: {service}",
                        message=f"{fails} consecutive failures",
                    ))
        except Exception as e:
            pass  # SMS module might not be imported yet
        return alerts

    def _check_error_handler(self) -> list[Alert]:
        """Check if error_handler has accumulated too many errors."""
        alerts = []
        try:
            from ..services.error_handler import error_handler
            stats = error_handler.get_stats()
            total = stats.get("total_errors", 0)
            by_type = stats.get("by_type", {})

            ban_count = by_type.get("ban", 0)
            if ban_count >= 5:
                alerts.append(Alert(
                    level=AlertLevel.CRITICAL,
                    category="error_accumulation",
                    title="Multiple account bans",
                    message=f"{ban_count} accounts banned during this session",
                ))

            limit_count = by_type.get("limit", 0)
            if limit_count >= 10:
                alerts.append(Alert(
                    level=AlertLevel.WARNING,
                    category="error_accumulation",
                    title="Rate limit hits",
                    message=f"{limit_count} rate limit errors — sending too fast?",
                ))
        except Exception as e:
            pass
        return alerts


# Singleton
alert_monitor = AlertMonitor()
