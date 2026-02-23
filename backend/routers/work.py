"""
Leomail v3 — Work (Mailing) Router
API endpoints for starting and managing mass mailing campaigns.
"""
from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Task, TaskStatus, ThreadLog
from loguru import logger

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
    max_link_uses: int = 0     # 0 = unlimited
    same_provider: bool = False
    threads: int = 10


@router.post("/start")
async def start_work(request: WorkRequest, background_tasks: BackgroundTasks):
    """Start mass mailing campaign in background."""
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
            t.details = "Остановлено пользователем (мгновенно)"
            t.stop_reason = "Остановлено пользователем"
        else:
            t.details = "Остановка: ждём завершения потоков..."
            t.stop_reason = "Остановлено пользователем (ожидание потоков)"
        stopped += 1

    if mode == "instant":
        threads = db.query(ThreadLog).filter(
            ThreadLog.thread_type == "work", ThreadLog.status == "running",
        ).all()
        for tl in threads:
            tl.status = "stopped"
            tl.current_action = "Остановлено"

    db.commit()
    logger.info(f"[Work] Stopped {stopped} task(s), mode={mode}")
    return {"stopped": stopped, "mode": mode}
