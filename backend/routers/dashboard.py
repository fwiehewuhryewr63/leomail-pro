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
        "version": "3.0",
        "configured": {
            "sms": bool(get_api_key("grizzly") or get_api_key("simsms")),
            "captcha": bool(get_api_key("capguru")),
        }
    }


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
    }
