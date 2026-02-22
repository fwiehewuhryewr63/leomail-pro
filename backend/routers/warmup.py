"""
Leomail v3 — Warmup Router
Cross-farm warmup: sender farms send TO receiver farms.
Receiver farms check inbox (inbox/spam), reply to emails.
"""
from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..database import get_db
from ..models import Task, TaskStatus, ThreadLog, WarmupEmail
from loguru import logger

router = APIRouter(prefix="/api/warmup", tags=["warmup"])

# Cancel set (same pattern as BIRTH_CANCEL)
WARMUP_CANCEL: set = set()


class WarmupRequest(BaseModel):
    sender_farm_ids: list[int]       # Farms whose accounts SEND
    receiver_farm_ids: list[int]     # Farms whose accounts RECEIVE + REPLY
    template_ids: list[int]
    phase_override: int = 0          # 0=auto (use account warmup_day), 1-5=force phase
    emails_per_day_min: int = 1
    emails_per_day_max: int = 5
    delay_min: int = 60              # seconds
    delay_max: int = 300             # seconds
    same_provider: bool = False
    threads: int = 5


@router.post("/start")
async def start_warmup(request: WarmupRequest, background_tasks: BackgroundTasks):
    """Start cross-farm warmup campaign in background."""
    if not request.sender_farm_ids or not request.receiver_farm_ids:
        return {"status": "error", "message": "Выберите фермы-отправители И фермы-получатели"}

    # Block same farm in both sender AND receiver
    overlap = set(request.sender_farm_ids) & set(request.receiver_farm_ids)
    if overlap:
        return {"status": "error", "message": f"Ферма не может быть одновременно отправителем и получателем (IDs: {overlap})"}

    from ..modules.warmup.engine import run_warmup_task
    background_tasks.add_task(
        run_warmup_task,
        sender_farm_ids=request.sender_farm_ids,
        receiver_farm_ids=request.receiver_farm_ids,
        template_ids=request.template_ids,
        phase_override=request.phase_override,
        emails_per_day_min=request.emails_per_day_min,
        emails_per_day_max=request.emails_per_day_max,
        delay_min=request.delay_min,
        delay_max=request.delay_max,
        same_provider=request.same_provider,
        threads=request.threads,
    )
    return {
        "status": "started",
        "message": (
            f"Прогрев запущен: {len(request.sender_farm_ids)} ферм-отправителей → "
            f"{len(request.receiver_farm_ids)} ферм-получателей, "
            f"фаза {'авто' if request.phase_override == 0 else request.phase_override}, "
            f"{request.threads} потоков"
        ),
    }


@router.get("/status")
async def warmup_status(db: Session = Depends(get_db)):
    """Check warmup task status."""
    running = db.query(Task).filter(
        Task.type == "warmup", Task.status == TaskStatus.RUNNING,
    ).order_by(Task.created_at.desc()).first()

    if running:
        return {
            "running": True,
            "task_id": running.id,
            "total": running.total_items or 0,
            "completed": running.completed_items or 0,
            "failed": running.failed_items or 0,
            "status": "running",
        }

    last = db.query(Task).filter(Task.type == "warmup").order_by(Task.created_at.desc()).first()
    if last:
        return {
            "running": False,
            "task_id": last.id,
            "total": last.total_items or 0,
            "completed": last.completed_items or 0,
            "failed": last.failed_items or 0,
            "status": last.status,
        }
    return {"running": False, "task_id": None}


@router.get("/stats/{task_id}")
async def warmup_stats(task_id: int, db: Session = Depends(get_db)):
    """Get delivery stats for a warmup task: inbox rate, spam rate, reply rate."""
    emails = db.query(WarmupEmail).filter(WarmupEmail.task_id == task_id).all()
    if not emails:
        return {"task_id": task_id, "total_sent": 0}

    total_sent = len(emails)
    checked = [e for e in emails if e.delivery_status != "pending"]
    inbox = [e for e in checked if e.delivery_status == "inbox"]
    spam = [e for e in checked if e.delivery_status == "spam"]
    not_found = [e for e in checked if e.delivery_status == "not_found"]
    replied = [e for e in emails if e.replied]

    total_checked = len(checked)
    return {
        "task_id": task_id,
        "total_sent": total_sent,
        "total_checked": total_checked,
        "inbox_count": len(inbox),
        "spam_count": len(spam),
        "not_found_count": len(not_found),
        "replied_count": len(replied),
        "inbox_rate": round(len(inbox) / total_checked * 100, 1) if total_checked > 0 else 0,
        "spam_rate": round(len(spam) / total_checked * 100, 1) if total_checked > 0 else 0,
        "reply_rate": round(len(replied) / total_sent * 100, 1) if total_sent > 0 else 0,
    }


@router.get("/stats/latest")
async def warmup_stats_latest(db: Session = Depends(get_db)):
    """Get stats for the most recent warmup task."""
    last = db.query(Task).filter(Task.type == "warmup").order_by(Task.created_at.desc()).first()
    if not last:
        return {"task_id": None, "total_sent": 0}
    return await warmup_stats(last.id, db)


@router.post("/stop")
async def stop_warmup(mode: str = "instant", db: Session = Depends(get_db)):
    """
    Stop warmup tasks.
    mode: "instant" = mark failed immediately, "graceful" = let threads finish current email
    """
    running = db.query(Task).filter(
        Task.type == "warmup", Task.status == TaskStatus.RUNNING,
    ).all()

    stopped = 0
    for t in running:
        WARMUP_CANCEL.add(t.id)
        if mode == "instant":
            t.status = TaskStatus.FAILED
            t.details = "Остановлено пользователем (мгновенно)"
        else:
            t.details = "Остановка: ждём завершения потоков..."
        stopped += 1

    # Stop running thread logs
    if mode == "instant":
        threads = db.query(ThreadLog).filter(
            ThreadLog.thread_type == "warmup", ThreadLog.status == "running",
        ).all()
        for tl in threads:
            tl.status = "stopped"
            tl.current_action = "Остановлено"

    db.commit()
    logger.info(f"[Warmup] Stopped {stopped} task(s), mode={mode}")
    return {"stopped": stopped, "mode": mode}
