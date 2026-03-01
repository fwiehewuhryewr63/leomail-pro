"""
Leomail v3 - Work (Mailing) Router
API endpoints for starting and managing mass mailing campaigns.
"""
from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Task, TaskStatus, ThreadLog
from loguru import logger
from ..services.engine_manager import engine_manager, EngineType

router = APIRouter(prefix="/api/work", tags=["work"])

# Cancel set
WORK_CANCEL: set = set()


class WorkRequest(BaseModel):
    farm_ids: list[int]
    database_ids: list[int]
    link_database_ids: list[int] = []
    template_ids: list[int]
    emails_per_day_min: int = 25
    emails_per_day_max: int = 75
    delay_min: int = 30        # seconds
    delay_max: int = 180       # seconds
    max_link_uses: int = 0     # 0 = unlimited per-link
    max_link_cycles: int = 0   # 0 = unlimited cycling, 1 = single pass
    same_provider: bool = False
    threads: int = 10


@router.post("/start")
async def start_work(request: WorkRequest, background_tasks: BackgroundTasks):
    """Start mass mailing campaign in background."""
    # Register with EngineManager
    try:
        engine_manager.start_engine(
            EngineType.CAMPAIGN,
            threads=request.threads,
            total_target=0,  # will be set by work engine
        )
    except RuntimeError:
        return {"status": "error", "message": "Campaign engine already running"}

    from ..modules.work.engine import run_work_task
    background_tasks.add_task(
        run_work_task,
        farm_ids=request.farm_ids,
        database_ids=request.database_ids,
        link_database_ids=request.link_database_ids,
        template_ids=request.template_ids,
        emails_per_day_min=request.emails_per_day_min,
        emails_per_day_max=request.emails_per_day_max,
        delay_min=request.delay_min,
        delay_max=request.delay_max,
        max_link_uses=request.max_link_uses,
        max_link_cycles=request.max_link_cycles,
        same_provider=request.same_provider,
        threads=request.threads,
    )
    return {
        "status": "started",
        "message": (
            f"Mailing started: {len(request.farm_ids)} farm(s), "
            f"{len(request.database_ids)} database(s), {request.threads} threads"
        ),
    }


@router.get("/status")
async def work_status(db: Session = Depends(get_db)):
    """Check work task status."""
    running = db.query(Task).filter(
        Task.type == "work", Task.status == TaskStatus.RUNNING,
    ).order_by(Task.created_at.desc()).first()

    if running:
        return {
            "running": True,
            "task_id": running.id,
            "total": running.total_items or 0,
            "completed": running.completed_items or 0,
            "failed": running.failed_items or 0,
            "status": "running",
            "stop_reason": running.stop_reason,
        }

    last = db.query(Task).filter(Task.type == "work").order_by(Task.created_at.desc()).first()
    if last:
        return {
            "running": False,
            "task_id": last.id,
            "total": last.total_items or 0,
            "completed": last.completed_items or 0,
            "failed": last.failed_items or 0,
            "status": last.status,
            "stop_reason": last.stop_reason,
        }
    return {"running": False, "task_id": None}


@router.post("/stop")
async def stop_work(mode: str = "instant", db: Session = Depends(get_db)):
    """
    Stop work tasks.
    mode: "instant" = mark failed immediately, "graceful" = let threads finish current email
    """
    running = db.query(Task).filter(
        Task.type == "work", Task.status == TaskStatus.RUNNING,
    ).all()

    stopped = 0
    for t in running:
        WORK_CANCEL.add(t.id)
        if mode == "instant":
            t.status = TaskStatus.FAILED
            t.details = "Stopped by user (instant)"
            t.stop_reason = "Stopped by user"
        else:
            t.details = "Stopping: waiting for threads to finish..."
            t.stop_reason = "Stopped by user (waiting for threads)"
        stopped += 1

    if mode == "instant":
        threads = db.query(ThreadLog).filter(
            ThreadLog.thread_type == "work", ThreadLog.status == "running",
        ).all()
        for tl in threads:
            tl.status = "stopped"
            tl.current_action = "Stopped"

    db.commit()
    # Also signal EngineManager
    engine_manager.stop_engine(EngineType.CAMPAIGN, mode)
    logger.info(f"[Work] Stopped {stopped} task(s), mode={mode}")
    return {"stopped": stopped, "mode": mode}


@router.get("/screenshot/{thread_id}")
async def work_thread_screenshot(thread_id: int):
    """Take a live screenshot of an active work browser thread."""
    from fastapi.responses import Response
    from ..modules.screenshot import live_screenshot
    png = await live_screenshot(thread_id)
    if png:
        return Response(content=png, media_type="image/png")
    return {"error": "Thread not active or no page available"}


@router.post("/estimate")
async def estimate_work(request: WorkRequest, db: Session = Depends(get_db)):
    """
    Pre-task resource calculator.
    Returns estimated time, capacity, and warnings without starting the task.
    """
    from ..models import Farm, Account, RecipientDatabase, LinkDatabase, Template, MailingStats
    from pathlib import Path
    import json

    warnings = []

    # 1. Accounts
    farms = db.query(Farm).filter(Farm.id.in_(request.farm_ids)).all()
    all_accounts = []
    for farm in farms:
        all_accounts.extend(farm.accounts)
    accounts = [a for a in all_accounts if a.status not in ("dead", "banned")]
    account_count = len(accounts)
    if account_count == 0:
        warnings.append("No alive accounts in selected farms")

    # 2. Recipients
    total_recipients = 0
    for db_id in request.database_ids:
        db_record = db.query(RecipientDatabase).get(db_id)
        if db_record:
            total_recipients += db_record.total_count or 0

    # Subtract already sent
    already_sent = db.query(MailingStats).filter(MailingStats.status == "sent").count()
    remaining = max(0, total_recipients - already_sent)
    if remaining == 0:
        warnings.append("All recipients already processed")

    # 3. Templates
    template_count = db.query(Template).filter(Template.id.in_(request.template_ids)).count()
    if template_count == 0:
        warnings.append("No templates")
    elif template_count < 3:
        warnings.append(f"Few templates ({template_count}) - frequent repeats")

    # 4. Links
    total_links = 0
    for ldb_id in request.link_database_ids:
        ldb = db.query(LinkDatabase).get(ldb_id)
        if ldb:
            total_links += ldb.total_count or 0

    # Effective links (with cycling)
    if total_links > 0:
        if request.max_link_cycles == 0 and request.max_link_uses == 0:
            effective_links = 999999  # unlimited
        elif request.max_link_cycles > 0 and request.max_link_uses == 0:
            effective_links = total_links * request.max_link_cycles
        elif request.max_link_cycles == 0 and request.max_link_uses > 0:
            effective_links = total_links * request.max_link_uses
        else:
            effective_links = total_links * min(request.max_link_cycles, request.max_link_uses)
    else:
        effective_links = 0

    if request.link_database_ids and effective_links > 0 and effective_links < remaining:
        warnings.append(f"Links ({effective_links}) less than recipients ({remaining}) - some emails will have no links")

    # 5. Capacity calculation
    avg_emails = (request.emails_per_day_min + request.emails_per_day_max) / 2
    total_capacity = int(account_count * avg_emails)
    if total_capacity > 0 and total_capacity < remaining:
        warnings.append(f"Capacity ({total_capacity} emails) less than recipients ({remaining}) - will take multiple days")

    # 6. ETA
    avg_delay = (request.delay_min + request.delay_max) / 2
    if account_count > 0 and avg_delay > 0:
        emails_per_hour = min(request.threads, account_count) * (3600 / avg_delay)
        estimated_hours = remaining / emails_per_hour if emails_per_hour > 0 else 0
    else:
        estimated_hours = 0

    has_critical = any(w.startswith("No ") or w.startswith("All ") for w in warnings)

    return {
        "accounts": account_count,
        "recipients": remaining,
        "recipients_total": total_recipients,
        "already_sent": already_sent,
        "templates": template_count,
        "links_total": total_links,
        "links_effective": effective_links if total_links > 0 else None,
        "emails_per_account_avg": int(avg_emails),
        "total_capacity": total_capacity,
        "estimated_hours": round(estimated_hours, 1),
        "warnings": warnings,
        "sufficient": not has_critical,
    }
