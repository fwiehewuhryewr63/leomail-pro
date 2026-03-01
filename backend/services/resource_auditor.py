"""
Leomail v4 - Resource Auditor
Background-cached health check for all system resources.
SMS/Captcha balances are refreshed every 60s in a background thread,
so the /health/resources endpoint returns instantly.
"""
import threading
import time
from loguru import logger
from sqlalchemy.orm import Session

from ..models import (
    Proxy, ProxyStatus, Campaign, CampaignStatus,
    CampaignTemplate, CampaignLink, CampaignRecipient,
)

# ---- Background balance cache ----
_balance_cache = {
    "sms": {"total_balance": 0, "estimated_accounts": 0, "providers": [], "status": "loading"},
    "captcha": {"balance": 0, "estimated_solves": 0, "providers": [], "status": "loading"},
}
_cache_lock = threading.Lock()
_cache_started = False
_REFRESH_INTERVAL = 60  # seconds


def _refresh_sms_balance() -> dict:
    """Fetch SMS provider balances (may take 15-20s per provider)."""
    total = 0.0
    providers = []
    try:
        from ..config import load_config
        config = load_config()
        sms_cfg = config.get("sms", {})
        for name in ["simsms", "grizzly", "5sim"]:
            key = sms_cfg.get(name, {}).get("api_key", "")
            if not key:
                continue
            try:
                if name == "simsms":
                    from ..services.simsms_provider import SimSmsProvider
                    bal = SimSmsProvider(key).get_balance()
                elif name == "grizzly":
                    from ..services.sms_provider import GrizzlySMS
                    bal = GrizzlySMS(key).get_balance()
                elif name == "5sim":
                    from ..services.fivesim_provider import FiveSimProvider
                    bal = FiveSimProvider(key).get_balance()
                else:
                    continue
                total += bal
                providers.append({"name": name, "balance": round(bal, 2)})
            except Exception as e:
                providers.append({"name": name, "balance": 0, "error": str(e)[:80]})
    except Exception:
        pass

    estimated_accounts = int(total / 0.20) if total > 0 else 0
    if total >= 10:
        status = "ok"
    elif total >= 2:
        status = "warning"
    else:
        status = "critical"

    return {
        "total_balance": round(total, 2),
        "estimated_accounts": estimated_accounts,
        "providers": providers,
        "status": status,
    }


def _refresh_captcha_balance() -> dict:
    """Fetch captcha provider balances (may take 5-15s per provider)."""
    total = 0.0
    providers = []
    try:
        from ..config import load_config
        config = load_config()
        cap_cfg = config.get("captcha", {})

        cap_key = cap_cfg.get("capguru", {}).get("api_key", "")
        if cap_key:
            try:
                from ..services.captcha_provider import CaptchaProvider
                bal = CaptchaProvider(cap_key).get_balance()
                total += bal
                providers.append({"name": "capguru", "balance": round(bal, 2)})
            except Exception as e:
                providers.append({"name": "capguru", "balance": 0, "error": str(e)[:80]})

        two_key = cap_cfg.get("twocaptcha", {}).get("api_key", "")
        if two_key:
            try:
                from ..services.captcha_provider import TwoCaptchaProvider
                bal = TwoCaptchaProvider(two_key).get_balance()
                total += bal
                providers.append({"name": "2captcha", "balance": round(bal, 2)})
            except Exception as e:
                providers.append({"name": "2captcha", "balance": 0, "error": str(e)[:80]})
    except Exception:
        pass

    if total >= 3:
        status = "ok"
    elif total >= 0.5:
        status = "warning"
    else:
        status = "critical"

    return {
        "balance": round(total, 2),
        "estimated_solves": int(total / 0.003) if total > 0 else 0,
        "providers": providers,
        "status": status,
    }


def _background_refresh_loop():
    """Daemon thread: refreshes SMS + captcha balances every 60s."""
    while True:
        try:
            # Refresh SMS and captcha in parallel threads for speed
            sms_result = [None]
            cap_result = [None]

            def _fetch_sms():
                sms_result[0] = _refresh_sms_balance()

            def _fetch_cap():
                cap_result[0] = _refresh_captcha_balance()

            t1 = threading.Thread(target=_fetch_sms, daemon=True)
            t2 = threading.Thread(target=_fetch_cap, daemon=True)
            t1.start()
            t2.start()
            t1.join(timeout=30)
            t2.join(timeout=30)

            with _cache_lock:
                if sms_result[0]:
                    _balance_cache["sms"] = sms_result[0]
                if cap_result[0]:
                    _balance_cache["captcha"] = cap_result[0]

            logger.debug(f"[ResourceAudit] Balances refreshed: SMS ${_balance_cache['sms']['total_balance']}, CAPTCHA ${_balance_cache['captcha']['balance']}")
        except Exception as e:
            logger.debug(f"[ResourceAudit] Refresh error: {e}")

        time.sleep(_REFRESH_INTERVAL)


def start_balance_cache():
    """Start the background balance refresh thread (call once on startup)."""
    global _cache_started
    if _cache_started:
        return
    _cache_started = True
    t = threading.Thread(target=_background_refresh_loop, daemon=True, name="balance-cache")
    t.start()
    logger.info("[ResourceAudit] Background balance cache started (60s refresh)")


def check_system_health(db: Session) -> dict:
    """
    Full system resource check.
    SMS/Captcha balances come from cache (instant).
    Proxy/Campaign data is from DB (fast).
    """
    # Ensure background cache is running
    start_balance_cache()

    with _cache_lock:
        sms_data = dict(_balance_cache["sms"])
        captcha_data = dict(_balance_cache["captcha"])

    health = {
        "sms": sms_data,
        "captcha": captcha_data,
        "proxies": _check_proxies(db),
        "campaigns": _check_campaigns(db),
    }

    # Overall status
    statuses = [
        health["sms"]["status"],
        health["captcha"]["status"],
        health["proxies"]["status"],
    ]
    for c in health["campaigns"]:
        statuses.append(c.get("resource_status", "ok"))

    if "critical" in statuses:
        health["overall"] = "critical"
    elif "warning" in statuses:
        health["overall"] = "warning"
    else:
        health["overall"] = "ok"

    return health


def _check_proxies(db: Session) -> dict:
    """Check proxy pool health (DB only - instant)."""
    alive = db.query(Proxy).filter(Proxy.status == ProxyStatus.ACTIVE).count()
    total = db.query(Proxy).count()
    dead = db.query(Proxy).filter(
        Proxy.status.in_([ProxyStatus.DEAD, ProxyStatus.BANNED, ProxyStatus.EXPIRED])
    ).count()

    if alive >= 20:
        status = "ok"
    elif alive >= 5:
        status = "warning"
    else:
        status = "critical"

    return {
        "alive": alive,
        "total": total,
        "dead": dead,
        "status": status,
    }


def _check_campaigns(db: Session) -> list[dict]:
    """Check resource status for each active/draft campaign (DB only - instant)."""
    campaigns = db.query(Campaign).filter(
        Campaign.status.in_([CampaignStatus.RUNNING, CampaignStatus.PAUSED, CampaignStatus.DRAFT])
    ).all()

    results = []
    for c in campaigns:
        active_templates = db.query(CampaignTemplate).filter(
            CampaignTemplate.campaign_id == c.id,
            CampaignTemplate.active == True  # noqa
        ).count()

        active_links = db.query(CampaignLink).filter(
            CampaignLink.campaign_id == c.id,
            CampaignLink.active == True  # noqa
        ).count()

        unsent = db.query(CampaignRecipient).filter(
            CampaignRecipient.campaign_id == c.id,
            CampaignRecipient.sent == False  # noqa
        ).count()

        issues = []
        if active_templates == 0:
            issues.append("No templates")
        if active_links == 0:
            issues.append("No links")
        if unsent == 0:
            issues.append("No recipients left")

        resource_status = "critical" if issues else "ok"
        if not issues and (active_links < 20 or unsent < 500):
            resource_status = "warning"

        results.append({
            "id": c.id,
            "name": c.name,
            "status": c.status,
            "templates": active_templates,
            "links": active_links,
            "recipients_remaining": unsent,
            "issues": issues,
            "resource_status": resource_status,
        })

    return results
