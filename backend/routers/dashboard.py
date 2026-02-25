from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Proxy, Account, Task, TaskStatus, Farm, Template, RecipientDatabase, Link, ThreadLog
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
        t.details = "Остановлено пользователем"
        t.stop_reason = "Остановлено пользователем (глобальная остановка)"
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
        tl.current_action = "Остановлено пользователем"
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
    """Full system resource health check — polled by dashboard."""
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
        },
        "farms": farms_count,
        "templates": templates_count,
        "databases": databases_count,
        "links": links_count,
        "active_tasks": running_tasks
    }


@router.get("/dashboard/stats")
async def dashboard_stats(db: Session = Depends(get_db)):
    """Flat stats for the frontend Dashboard.jsx."""
    from sqlalchemy import func
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
    inbox_rate = round((total_sent / total_mailed * 100), 1) if total_mailed > 0 else 0

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
        ).count()  # Global sent — ideally per-DB, but we track globally
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

    return {
        "total_accounts": total_accounts,
        "total_farms": total_farms,
        "total_proxies": total_proxies,
        "total_templates": total_templates,
        "total_databases": databases_count,
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
            "inbox_rate": inbox_rate,
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
    }
