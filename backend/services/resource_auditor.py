"""
Leomail v4 - Resource Auditor
Standalone health check for all system resources.
Polled by dashboard for real-time status.
"""
from loguru import logger
from sqlalchemy.orm import Session

from ..models import (
    Proxy, ProxyStatus, Campaign, CampaignStatus,
    CampaignTemplate, CampaignLink, CampaignRecipient,
)


def check_system_health(db: Session) -> dict:
    """
    Full system resource check.
    Returns health status for all resources: SMS, Captcha, Proxies, and per-campaign.
    """
    health = {
        "sms": _check_sms(),
        "captcha": _check_captcha(),
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


def _check_sms() -> dict:
    """Check SMS provider balances."""
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


def _check_captcha() -> dict:
    """Check captcha provider balances (CapGuru + 2Captcha)."""
    total = 0.0
    providers = []
    try:
        from ..config import load_config
        config = load_config()
        cap_cfg = config.get("captcha", {})

        # CapGuru (reCAPTCHA v2/v3)
        cap_key = cap_cfg.get("capguru", {}).get("api_key", "")
        if cap_key:
            try:
                from ..services.captcha_provider import CaptchaProvider
                bal = CaptchaProvider(cap_key).get_balance()
                total += bal
                providers.append({"name": "capguru", "balance": round(bal, 2)})
            except Exception as e:
                providers.append({"name": "capguru", "balance": 0, "error": str(e)[:80]})

        # 2Captcha (FunCaptcha / Arkose Labs)
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


def _check_proxies(db: Session) -> dict:
    """Check proxy pool health."""
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
    """Check resource status for each active/draft campaign."""
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
