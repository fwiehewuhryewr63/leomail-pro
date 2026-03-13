from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Proxy, Account, Task, TaskStatus, Farm, Template, RecipientDatabase, Link, ThreadLog, NamePack
from ..config import load_config, get_api_key
from loguru import logger

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.post("/tasks/stop-all")
async def stop_all_tasks(db: Session = Depends(get_db)):
    """Stop ALL running tasks (birth, warmup, work)."""
    running_tasks = db.query(Task).filter(Task.status.in_(["running", "pending"])).all()
    running_threads = db.query(ThreadLog).filter(ThreadLog.status == "running").all()

    stopped_tasks = 0
    stopped_threads = 0

    # Stop all tasks
    for t in running_tasks:
        t.status = TaskStatus.FAILED
        t.details = "Stopped by user"
        t.stop_reason = "Stopped by user (global stop)"
        stopped_tasks += 1

        # If birth task, add to BIRTH_CANCEL set for in-flight workers
        if t.type == "birth":
            try:
                from .birth import BIRTH_CANCEL
                BIRTH_CANCEL.add(t.id)
            except Exception:
                pass

    # Clean up running threads
    for tl in running_threads:
        tl.status = "stopped"
        tl.current_action = "Stopped by user"
        stopped_threads += 1

    db.commit()
    logger.info(f"[Stop-All] Stopped {stopped_tasks} task(s), {stopped_threads} thread(s)")

    return {
        "stopped_tasks": stopped_tasks,
        "stopped_threads": stopped_threads,
        "status": "stopped",
    }


@router.get("/health")
async def health_check():
    config = load_config()
    return {
        "status": "online",
        "version": "4.0",
        "configured": {
            "sms": bool(get_api_key("grizzly") or get_api_key("simsms")),
            "captcha": bool(get_api_key("capguru")),
        }
    }


@router.get("/health/resources")
async def resource_health(db: Session = Depends(get_db)):
    """Full system resource health check - polled by dashboard."""
    from ..services.resource_auditor import check_system_health
    return check_system_health(db)


@router.get("/dashboard")
async def dashboard(db: Session = Depends(get_db)):
    # Account stats
    total_accounts = db.query(Account).count()
    accounts_new = db.query(Account).filter(Account.status == "new").count()
    accounts_warming = db.query(Account).filter(Account.status.in_(["phase_1", "phase_2", "phase_3", "phase_4", "phase_5"])).count()
    accounts_warmed = db.query(Account).filter(Account.status == "warmed").count()
    accounts_sending = db.query(Account).filter(Account.status == "sending").count()
    accounts_dead = db.query(Account).filter(Account.status.in_(["dead", "banned"])).count()

    # Proxy stats
    total_proxies = db.query(Proxy).count()
    proxies_alive = db.query(Proxy).filter(Proxy.status == "active").count()
    proxies_dead = db.query(Proxy).filter(Proxy.status == "dead").count()
    proxies_exhausted = db.query(Proxy).filter(Proxy.status == "exhausted").count()

    # Other counts
    farms_count = db.query(Farm).count()
    templates_count = db.query(Template).count()
    databases_count = db.query(RecipientDatabase).count()
    links_count = db.query(Link).count()

    # Active tasks
    running_tasks = db.query(Task).filter(Task.status == "running").count()

    return {
        "accounts": {
            "total": total_accounts,
            "new": accounts_new,
            "warming": accounts_warming,
            "warmed": accounts_warmed,
            "sending": accounts_sending,
            "dead": accounts_dead
        },
        "proxies": {
            "total": total_proxies,
            "alive": proxies_alive,
            "dead": proxies_dead,
            "exhausted": proxies_exhausted,
        },
        "farms": farms_count,
        "templates": templates_count,
        "databases": databases_count,
        "links": links_count,
        "active_tasks": running_tasks
    }


@router.get("/dashboard/stats")
async def dashboard_stats(db: Session = Depends(get_db), days: int = 7):
    """Flat stats for the frontend Dashboard.jsx."""
    from sqlalchemy import func
    from datetime import datetime, timedelta
    from ..models import MailingStats

    total_accounts = db.query(Account).count()
    total_farms = db.query(Farm).count()
    total_proxies = db.query(Proxy).count()
    total_templates = db.query(Template).count()
    
    status_new = db.query(Account).filter(Account.status == "new").count()
    status_warmup = db.query(Account).filter(Account.status.in_(["phase_1", "phase_2", "phase_3", "phase_4", "phase_5"])).count()
    status_warmed = db.query(Account).filter(Account.status == "warmed").count()
    status_working = db.query(Account).filter(Account.status == "sending").count()
    status_paused = db.query(Account).filter(Account.status == "paused").count()
    status_dead = db.query(Account).filter(Account.status.in_(["dead", "banned"])).count()
    
    proxies_alive = db.query(Proxy).filter(Proxy.status == "active").count()
    proxies_dead = db.query(Proxy).filter(Proxy.status == "dead").count()
    
    running_tasks = db.query(Task).filter(Task.status == "running").count()
    databases_count = db.query(RecipientDatabase).count()
    links_count = db.query(Link).count()
    names_count = db.query(NamePack).count()

    # Per-provider breakdown
    provider_rows = db.query(Account.provider, func.count()).group_by(Account.provider).all()
    by_provider = {row[0] or "unknown": row[1] for row in provider_rows}

    # Per-provider × per-status matrix
    provider_status_rows = db.query(
        Account.provider, Account.status, func.count()
    ).group_by(Account.provider, Account.status).all()
    by_provider_status = {}
    for provider, status, cnt in provider_status_rows:
        prov = provider or "unknown"
        if prov not in by_provider_status:
            by_provider_status[prov] = {}
        by_provider_status[prov][status or "new"] = cnt

    # ─── MAILING STATS ───
    total_sent = db.query(MailingStats).filter(MailingStats.status == "sent").count()
    total_errors = db.query(MailingStats).filter(MailingStats.status == "error").count()
    total_bounced = db.query(MailingStats).filter(MailingStats.status == "bounce").count()
    total_limited = db.query(MailingStats).filter(MailingStats.status == "limit").count()
    total_mailed = total_sent + total_errors + total_bounced + total_limited
    delivery_rate = round((total_sent / total_mailed * 100), 1) if total_mailed > 0 else 0

    # ─── FARM HEALTH ───
    farm_health = []
    all_farms = db.query(Farm).all()
    for farm in all_farms:
        accs = farm.accounts
        if not accs:
            continue
        total = len(accs)
        active = sum(1 for a in accs if a.status not in ("dead", "banned", "paused"))
        banned = sum(1 for a in accs if a.status in ("dead", "banned"))
        warmed = sum(1 for a in accs if a.status == "warmed")
        sending = sum(1 for a in accs if a.status == "sending")
        farm_health.append({
            "id": farm.id, "name": farm.name,
            "total": total, "active": active, "banned": banned,
            "warmed": warmed, "sending": sending,
            "health_pct": round(active / total * 100) if total > 0 else 0,
        })

    # ─── DATABASE PROGRESS ───
    database_progress = []
    all_dbs = db.query(RecipientDatabase).all()
    for rdb in all_dbs:
        sent_count = db.query(MailingStats).filter(
            MailingStats.status == "sent",
        ).count()  # Global sent - ideally per-DB, but we track globally
        database_progress.append({
            "id": rdb.id, "name": rdb.name,
            "total": rdb.total_count or 0,
            "used": rdb.used_count or 0,
            "remaining": max(0, (rdb.total_count or 0) - (rdb.used_count or 0)),
        })

    # ─── THREAD STATS ───
    completed_ok = db.query(ThreadLog).filter(ThreadLog.status == "done").count()
    completed_err = db.query(ThreadLog).filter(ThreadLog.status.in_(["error", "stopped"])).count()
    running_threads = db.query(ThreadLog).filter(ThreadLog.status == "running").count()

    # ─── COMPLETED TASKS ───
    completed_tasks = db.query(Task).filter(Task.status.in_(["done", "completed"])).count()
    failed_tasks = db.query(Task).filter(Task.status == "failed").count()

    # ─── ACTIVITY DATA (per-day for chart) ───
    days = min(max(days, 1), 30)  # clamp 1-30
    now = datetime.utcnow()
    activity_data = []
    for i in range(days - 1, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        day_label = day_start.strftime("%d %b")

        accs_created = 0
        emails_sent = 0
        try:
            accs_created = db.query(Account).filter(
                Account.created_at >= day_start,
                Account.created_at < day_end,
            ).count()
        except Exception:
            pass
        try:
            emails_sent = db.query(MailingStats).filter(
                MailingStats.sent_at >= day_start,
                MailingStats.sent_at < day_end,
                MailingStats.status == "sent",
            ).count()
        except Exception:
            pass

        activity_data.append({
            "date": day_label,
            "accounts": accs_created,
            "emails": emails_sent,
        })

    # ─── RECENT ACTIVITY (last 10 events) ───
    recent_activity = []
    try:
        recent_threads = db.query(ThreadLog).order_by(ThreadLog.id.desc()).limit(10).all()
        for tl in recent_threads:
            ts = ""
            if tl.started_at:
                ts = tl.started_at.strftime("%H:%M")
            atype = "info"
            if tl.status == "done":
                atype = "success"
            elif tl.status in ("error", "stopped"):
                atype = "error"
            msg = tl.current_action or tl.status or "—"
            if tl.status == "done" and tl.account_email:
                msg = f"Registered {tl.account_email}"
            recent_activity.append({"time": ts, "type": atype, "message": msg})
    except Exception:
        pass

    return {
        "total_accounts": total_accounts,
        "total_farms": total_farms,
        "total_proxies": total_proxies,
        "total_templates": total_templates,
        "total_databases": databases_count,
        "total_links": links_count,
        "total_names": names_count,
        "status_new": status_new,
        "status_warmup": status_warmup,
        "status_warmed": status_warmed,
        "status_working": status_working,
        "status_paused": status_paused,
        "status_dead": status_dead,
        "proxies_alive": proxies_alive,
        "proxies_dead": proxies_dead,
        "active_tasks": running_tasks,
        "by_provider": by_provider,
        "by_provider_status": by_provider_status,
        # New stats
        "mailing_stats": {
            "total_sent": total_sent,
            "total_errors": total_errors,
            "total_bounced": total_bounced,
            "total_limited": total_limited,
            "delivery_rate": delivery_rate,
            "inbox_rate": delivery_rate,  # backward compat for older frontend builds
        },
        "farm_health": farm_health,
        "database_progress": database_progress,
        "thread_stats": {
            "completed_ok": completed_ok,
            "completed_err": completed_err,
            "running": running_threads,
        },
        "task_stats": {
            "completed": completed_tasks,
            "failed": failed_tasks,
            "running": running_tasks,
        },
        "activity_data": activity_data,
        "recent_activity": recent_activity,
    }


@router.get("/dashboard/analytics")
async def dashboard_analytics(db: Session = Depends(get_db)):
    """
    Advanced analytics - IMAP rates, proxy cooldown, browser memory, SMS backoff.
    Covers all new features from Steps 1-9.
    """
    from sqlalchemy import func
    from datetime import datetime, timedelta

    # ── IMAP Verification Stats ──
    imap_total = db.query(Account).filter(Account.imap_checked_at != None).count()  # noqa: E711
    imap_verified = db.query(Account).filter(Account.imap_verified == True).count()  # noqa: E712
    imap_failed = imap_total - imap_verified
    imap_unchecked = db.query(Account).filter(Account.imap_checked_at == None).count()  # noqa: E711
    imap_rate = round((imap_verified / imap_total * 100), 1) if imap_total > 0 else 0

    # Per-provider IMAP breakdown
    imap_by_provider = {}
    for row in db.query(
        Account.provider,
        func.count().label("total"),
    ).filter(Account.imap_checked_at != None).group_by(Account.provider).all():  # noqa: E711
        prov = row[0] or "unknown"
        total = row[1] or 0
        verified = db.query(Account).filter(
            Account.provider == row[0],
            Account.imap_verified == True,  # noqa: E712
        ).count()
        imap_by_provider[prov] = {
            "total": total,
            "verified": verified,
            "failed": total - verified,
            "rate": round((verified / total * 100), 1) if total > 0 else 0,
        }

    # ── Proxy Cooldown Status ──
    now = datetime.utcnow()
    cooldown_30min = now - timedelta(minutes=30)
    cooldown_15min = now - timedelta(minutes=15)

    proxies_active = db.query(Proxy).filter(Proxy.status == "active").count()
    proxies_on_cooldown_30 = db.query(Proxy).filter(
        Proxy.status == "active",
        Proxy.last_used_at != None,  # noqa: E711
        Proxy.last_used_at > cooldown_30min,
    ).count()
    proxies_on_cooldown_15 = db.query(Proxy).filter(
        Proxy.status == "active",
        Proxy.last_used_at != None,  # noqa: E711
        Proxy.last_used_at > cooldown_15min,
    ).count()
    proxies_available_yahoo = proxies_active - proxies_on_cooldown_30
    proxies_available_outlook = proxies_active - proxies_on_cooldown_15

    # ── Browser Memory ──
    browser_memory_mb = 0
    try:
        from ..services.browser_leak_guard import get_browser_memory_usage_mb
        browser_memory_mb = round(get_browser_memory_usage_mb(), 1)
    except Exception:
        pass

    # ── SMS Backoff Status ──
    sms_backoff_status = {}
    try:
        from ..modules.birth._helpers import _sms_backoff, _get_sms_backoff_delay
        for service, info in _sms_backoff.items():
            sms_backoff_status[service] = {
                "consecutive_fails": info.get("fails", 0),
                "next_delay_seconds": round(_get_sms_backoff_delay(service), 0),
            }
    except Exception:
        pass

    # ── Birth Success Rate (last 24h) ──
    since_24h = now - timedelta(hours=24)
    births_ok = db.query(ThreadLog).filter(
        ThreadLog.status == "done",
        ThreadLog.created_at > since_24h,
    ).count()
    births_fail = db.query(ThreadLog).filter(
        ThreadLog.status.in_(["error", "stopped"]),
        ThreadLog.created_at > since_24h,
    ).count()
    births_total = births_ok + births_fail
    birth_success_rate = round((births_ok / births_total * 100), 1) if births_total > 0 else 0

    return {
        "imap": {
            "total_checked": imap_total,
            "verified": imap_verified,
            "failed": imap_failed,
            "unchecked": imap_unchecked,
            "success_rate": imap_rate,
            "by_provider": imap_by_provider,
        },
        "proxy_cooldown": {
            "total_active": proxies_active,
            "on_cooldown_30min": proxies_on_cooldown_30,
            "on_cooldown_15min": proxies_on_cooldown_15,
            "available_for_yahoo": proxies_available_yahoo,
            "available_for_outlook": proxies_available_outlook,
        },
        "browser": {
            "memory_usage_mb": browser_memory_mb,
        },
        "sms_backoff": sms_backoff_status,
        "birth_24h": {
            "success": births_ok,
            "failed": births_fail,
            "total": births_total,
            "success_rate": birth_success_rate,
        },
    }


@router.get("/dashboard/autoreg-analytics")
async def autoreg_analytics(db: Session = Depends(get_db)):
    """
    Advanced autoreg analytics:
    - Per-provider success rates (1d, 7d, 30d, all-time)
    - Top failure reasons aggregated
    - Account lifetime metrics (avg age, survival rates)
    """
    from sqlalchemy import func, case
    from datetime import datetime, timedelta
    from collections import Counter

    now = datetime.utcnow()
    periods = {
        "1d": now - timedelta(days=1),
        "7d": now - timedelta(days=7),
        "30d": now - timedelta(days=30),
        "all": datetime(2020, 1, 1),  # effectively all-time
    }

    # ── Per-provider autoreg success rates ──
    provider_rates = {}
    # Extract provider from account_email domain
    all_threads = db.query(
        ThreadLog.account_email,
        ThreadLog.status,
        ThreadLog.error_message,
        ThreadLog.started_at,
    ).filter(
        ThreadLog.thread_type.in_(["birth", "autoreg"]),
    ).all()

    # Map email domains to provider names
    domain_to_provider = {
        "gmail.com": "gmail", "yahoo.com": "yahoo", "aol.com": "aol",
        "outlook.com": "outlook", "hotmail.com": "hotmail",
        "proton.me": "proton", "protonmail.com": "proton",
        "web.de": "webde",
    }

    for period_name, period_start in periods.items():
        period_threads = [t for t in all_threads if t.started_at and t.started_at >= period_start]
        by_provider = {}

        for t in period_threads:
            # Determine provider from email
            provider = "unknown"
            if t.account_email and "@" in t.account_email:
                domain = t.account_email.split("@")[1].lower()
                provider = domain_to_provider.get(domain, domain.split(".")[0])

            if provider not in by_provider:
                by_provider[provider] = {"success": 0, "failed": 0, "total": 0}

            by_provider[provider]["total"] += 1
            if t.status == "done":
                by_provider[provider]["success"] += 1
            elif t.status in ("error", "stopped"):
                by_provider[provider]["failed"] += 1

        # Calculate rates
        for prov, stats in by_provider.items():
            stats["rate"] = round(
                (stats["success"] / stats["total"] * 100), 1
            ) if stats["total"] > 0 else 0

        provider_rates[period_name] = by_provider

    # ── Top failure reasons ──
    error_threads = [t for t in all_threads if t.status in ("error", "stopped") and t.error_message]
    failure_reasons = Counter()

    # Categorize error messages into readable reasons
    for t in error_threads:
        msg = (t.error_message or "").lower()
        if "captcha" in msg:
            failure_reasons["CAPTCHA failed"] += 1
        elif "sms" in msg or "phone" in msg or "number" in msg:
            failure_reasons["SMS/phone verification failed"] += 1
        elif "proxy" in msg:
            failure_reasons["Proxy error"] += 1
        elif "ban" in msg or "block" in msg or "suspended" in msg:
            failure_reasons["Account blocked/banned"] += 1
        elif "rate" in msg or "limit" in msg or "too many" in msg:
            failure_reasons["Rate limited"] += 1
        elif "timeout" in msg or "timed out" in msg:
            failure_reasons["Timeout"] += 1
        elif "selector" in msg or "element" in msg or "locator" in msg:
            failure_reasons["UI selector changed"] += 1
        elif "network" in msg or "connection" in msg or "dns" in msg:
            failure_reasons["Network error"] += 1
        elif "username" in msg or "email" in msg and "taken" in msg:
            failure_reasons["Username/email taken"] += 1
        else:
            failure_reasons["Other"] += 1

    top_failures = [
        {"reason": reason, "count": count}
        for reason, count in failure_reasons.most_common(10)
    ]

    # Per-provider failure breakdown
    provider_failures = {}
    for t in error_threads:
        provider = "unknown"
        if t.account_email and "@" in t.account_email:
            domain = t.account_email.split("@")[1].lower()
            provider = domain_to_provider.get(domain, domain.split(".")[0])

        if provider not in provider_failures:
            provider_failures[provider] = Counter()

        msg = (t.error_message or "").lower()
        if "captcha" in msg:
            provider_failures[provider]["CAPTCHA"] += 1
        elif "sms" in msg or "phone" in msg:
            provider_failures[provider]["SMS"] += 1
        elif "proxy" in msg:
            provider_failures[provider]["Proxy"] += 1
        elif "ban" in msg or "block" in msg:
            provider_failures[provider]["Blocked"] += 1
        elif "rate" in msg or "limit" in msg:
            provider_failures[provider]["Rate limit"] += 1
        else:
            provider_failures[provider]["Other"] += 1

    provider_failures_dict = {
        prov: dict(counter.most_common(5))
        for prov, counter in provider_failures.items()
    }

    # ── Account lifetime metrics ──
    all_accounts = db.query(
        Account.created_at, Account.status, Account.provider
    ).filter(Account.created_at != None).all()  # noqa: E711

    # Average age of dead/banned accounts
    dead_ages = []
    alive_ages = []
    for acc in all_accounts:
        if not acc.created_at:
            continue
        age_days = (now - acc.created_at).days

        if acc.status in ("dead", "banned"):
            dead_ages.append(age_days)
        elif acc.status not in ("dead", "banned"):
            alive_ages.append(age_days)

    avg_dead_age = round(sum(dead_ages) / len(dead_ages), 1) if dead_ages else 0
    avg_alive_age = round(sum(alive_ages) / len(alive_ages), 1) if alive_ages else 0

    # Survival rates (% of accounts created N+ days ago that are still alive)
    survival = {}
    for days_threshold in [7, 30, 90]:
        cutoff = now - timedelta(days=days_threshold)
        old_accounts = [a for a in all_accounts if a.created_at and a.created_at <= cutoff]
        if old_accounts:
            alive = sum(1 for a in old_accounts if a.status not in ("dead", "banned"))
            survival[f"{days_threshold}d"] = round(alive / len(old_accounts) * 100, 1)
        else:
            survival[f"{days_threshold}d"] = 0

    # Per-provider lifetime
    provider_lifetime = {}
    for acc in all_accounts:
        prov = acc.provider or "unknown"
        if prov not in provider_lifetime:
            provider_lifetime[prov] = {"alive": 0, "dead": 0, "dead_ages": []}
        if acc.status in ("dead", "banned"):
            provider_lifetime[prov]["dead"] += 1
            if acc.created_at:
                provider_lifetime[prov]["dead_ages"].append((now - acc.created_at).days)
        else:
            provider_lifetime[prov]["alive"] += 1

    provider_lifetime_clean = {}
    for prov, data in provider_lifetime.items():
        avg_age = round(sum(data["dead_ages"]) / len(data["dead_ages"]), 1) if data["dead_ages"] else 0
        total = data["alive"] + data["dead"]
        provider_lifetime_clean[prov] = {
            "alive": data["alive"],
            "dead": data["dead"],
            "total": total,
            "survival_rate": round(data["alive"] / total * 100, 1) if total > 0 else 0,
            "avg_dead_age_days": avg_age,
        }

    return {
        "provider_success_rates": provider_rates,
        "top_failures": top_failures,
        "provider_failures": provider_failures_dict,
        "lifetime": {
            "avg_dead_age_days": avg_dead_age,
            "avg_alive_age_days": avg_alive_age,
            "survival_rates": survival,
            "by_provider": provider_lifetime_clean,
        },
    }


# ─── Warmup Analytics ────────────────────────────────────────────────────────

@router.get("/dashboard/warmup-analytics")
async def warmup_analytics(db: Session = Depends(get_db)):
    """
    Warmup-specific analytics:
    - Phase distribution with health scores
    - Daily send/reply/star stats
    - Per-provider warmup progress
    - Peer-to-peer delivery tracking
    """
    from sqlalchemy import func
    from datetime import datetime, timedelta
    from ..models import Account, AccountStatus, WarmupEmail

    warming_statuses = [
        AccountStatus.PHASE_1, AccountStatus.PHASE_2,
        AccountStatus.PHASE_3, AccountStatus.PHASE_4, AccountStatus.PHASE_5,
    ]

    # ── Phase distribution with health ──
    phase_data = {}
    for status in warming_statuses + [AccountStatus.WARMED, AccountStatus.NEW]:
        accs = db.query(Account).filter(Account.status == status).all()
        if accs:
            avg_health = sum(a.health_score or 100 for a in accs) / len(accs)
            avg_day = sum(a.warmup_day or 0 for a in accs) / len(accs)
            total_sent = sum(a.total_emails_sent or 0 for a in accs)
            phase_data[status.value] = {
                "count": len(accs),
                "avg_health": round(avg_health, 1),
                "avg_day": round(avg_day, 1),
                "total_sent": total_sent,
            }

    # ── Overall warmup stats ──
    all_warming = db.query(Account).filter(Account.status.in_(warming_statuses)).all()
    overall_avg_health = 0
    overall_avg_day = 0
    if all_warming:
        overall_avg_health = round(sum(a.health_score or 100 for a in all_warming) / len(all_warming), 1)
        overall_avg_day = round(sum(a.warmup_day or 0 for a in all_warming) / len(all_warming), 1)

    # ── Per-provider warmup progress ──
    provider_progress = {}
    for row in db.query(
        Account.provider, Account.status, func.count()
    ).filter(
        Account.status.in_(warming_statuses + [AccountStatus.WARMED])
    ).group_by(Account.provider, Account.status).all():
        prov = row[0] or "unknown"
        if prov not in provider_progress:
            provider_progress[prov] = {}
        provider_progress[prov][row[1] or "unknown"] = row[2]

    # ── Peer-to-peer delivery stats (from WarmupEmail) ──
    try:
        total_warmup_emails = db.query(WarmupEmail).count()
        inbox_count = db.query(WarmupEmail).filter(WarmupEmail.delivery_status == "inbox").count()
        spam_count = db.query(WarmupEmail).filter(WarmupEmail.delivery_status == "spam").count()
        replied_count = db.query(WarmupEmail).filter(WarmupEmail.replied == True).count()  # noqa: E712
        warmup_email_stats = {
            "total": total_warmup_emails,
            "inbox": inbox_count,
            "spam": spam_count,
            "replied": replied_count,
            "inbox_rate": round(inbox_count / total_warmup_emails * 100, 1) if total_warmup_emails > 0 else 0,
            "reply_rate": round(replied_count / total_warmup_emails * 100, 1) if total_warmup_emails > 0 else 0,
        }
    except Exception:
        warmup_email_stats = {"total": 0, "inbox": 0, "spam": 0, "replied": 0, "inbox_rate": 0, "reply_rate": 0}

    # ── Health score distribution (histogram) ──
    health_buckets = {"0-20": 0, "21-40": 0, "41-60": 0, "61-80": 0, "81-100": 0}
    for acc in all_warming:
        h = acc.health_score or 100
        if h <= 20:
            health_buckets["0-20"] += 1
        elif h <= 40:
            health_buckets["21-40"] += 1
        elif h <= 60:
            health_buckets["41-60"] += 1
        elif h <= 80:
            health_buckets["61-80"] += 1
        else:
            health_buckets["81-100"] += 1

    return {
        "phases": phase_data,
        "overall": {
            "warming_count": len(all_warming),
            "warmed_count": db.query(Account).filter(Account.status == AccountStatus.WARMED).count(),
            "avg_health": overall_avg_health,
            "avg_day": overall_avg_day,
        },
        "provider_progress": provider_progress,
        "warmup_emails": warmup_email_stats,
        "health_distribution": health_buckets,
    }


# ─── System Alerts ────────────────────────────────────────────────────────────

@router.get("/dashboard/alerts")
async def system_alerts(db: Session = Depends(get_db)):
    """
    Threshold-based system health alerts.
    Returns active alerts sorted by severity.
    """
    from ..services.alert_monitor import alert_monitor
    alerts = alert_monitor.check_all(db)
    # Sort: critical first, then warning, then info
    level_order = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: level_order.get(a.level, 3))
    return {
        "alerts": [a.to_dict() for a in alerts],
        "counts": {
            "critical": sum(1 for a in alerts if a.level == "critical"),
            "warning": sum(1 for a in alerts if a.level == "warning"),
            "info": sum(1 for a in alerts if a.level == "info"),
        },
    }


# ─── Per-Campaign Stats ──────────────────────────────────────────────────────

@router.get("/dashboard/campaign-stats")
async def campaign_delivery_stats(db: Session = Depends(get_db)):
    """
    Per-campaign delivery breakdown: sent, errors, bounced, delivery rate.
    """
    from sqlalchemy import func
    from ..models import Campaign, MailingStats

    results = []
    campaigns = db.query(Campaign).all()
    for c in campaigns:
        sent = db.query(MailingStats).filter(
            MailingStats.campaign_id == c.id, MailingStats.status == "sent"
        ).count()
        errors = db.query(MailingStats).filter(
            MailingStats.campaign_id == c.id, MailingStats.status == "error"
        ).count()
        bounced = db.query(MailingStats).filter(
            MailingStats.campaign_id == c.id, MailingStats.status == "bounce"
        ).count()
        limited = db.query(MailingStats).filter(
            MailingStats.campaign_id == c.id, MailingStats.status == "limit"
        ).count()
        total = sent + errors + bounced + limited
        delivery_rate = round(sent / total * 100, 1) if total > 0 else 0

        results.append({
            "id": c.id,
            "name": c.name,
            "status": c.status,
            "sent": sent,
            "errors": errors,
            "bounced": bounced,
            "limited": limited,
            "delivery_rate": delivery_rate,
            "inbox_rate": delivery_rate,  # backward compat for older frontend builds
            "total_recipients": len(c.recipients) if c.recipients else 0,
        })

    return {"campaigns": results}


# ─── Cost Analytics ───────────────────────────────────────────────────────────

@router.get("/dashboard/costs")
async def cost_analytics():
    """
    Cost analytics: session totals + today's spending + 7-day daily breakdown.
    """
    from ..services.cost_tracker import cost_tracker

    return {
        "session": cost_tracker.get_session_totals(),
        "today": cost_tracker.get_today_summary(),
        "daily": cost_tracker.get_daily_breakdown(7),
    }


# ─── Task Report ─────────────────────────────────────────────────────────────

@router.get("/dashboard/task-report/{task_id}")
async def task_completion_report(task_id: int):
    """
    Post-task resource consumption report.
    SMS ordered/cancelled, captcha solved, proxies used, cost per account.
    """
    from ..services.task_report import task_report

    report = task_report.generate(task_id)
    return report
