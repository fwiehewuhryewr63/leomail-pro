"""
Leomail v3 - Statistics Router
API endpoints for mailing campaign stats and reports.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from ..database import get_db
from ..models import MailingStats, Task

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/summary")
async def get_summary(db: Session = Depends(get_db)):
    """Overall mailing stats summary."""
    total_sent = db.query(func.count(MailingStats.id)).filter(
        MailingStats.status == "sent"
    ).scalar() or 0

    total_errors = db.query(func.count(MailingStats.id)).filter(
        MailingStats.status == "error"
    ).scalar() or 0

    total_bounces = db.query(func.count(MailingStats.id)).filter(
        MailingStats.status == "bounce"
    ).scalar() or 0

    total_limits = db.query(func.count(MailingStats.id)).filter(
        MailingStats.status == "limit"
    ).scalar() or 0

    total_attempts = total_sent + total_errors + total_bounces + total_limits
    delivery_rate = round(total_sent / max(1, total_attempts) * 100, 1)

    return {
        "total_sent": total_sent,
        "total_errors": total_errors,
        "total_bounces": total_bounces,
        "total_limits": total_limits,
        "total_attempts": total_attempts,
        "delivery_rate": delivery_rate,
        "success_rate": delivery_rate,
    }


@router.get("/by-account")
async def stats_by_account(db: Session = Depends(get_db)):
    """Per-account breakdown."""
    rows = (
        db.query(
            MailingStats.account_email,
            MailingStats.provider,
            MailingStats.status,
            func.count(MailingStats.id),
        )
        .group_by(MailingStats.account_email, MailingStats.provider, MailingStats.status)
        .all()
    )

    # Group by account
    accounts = {}
    for email, provider, status, count in rows:
        if email not in accounts:
            accounts[email] = {
                "email": email,
                "provider": provider or "unknown",
                "sent": 0,
                "errors": 0,
                "bounces": 0,
                "limits": 0,
            }
        accounts[email][status + "s" if status != "sent" else "sent"] = count
        if status == "sent":
            accounts[email]["sent"] = count

    for account in accounts.values():
        total_attempts = (
            account["sent"]
            + account["errors"]
            + account["bounces"]
            + account["limits"]
        )
        account["total_attempts"] = total_attempts
        account["delivery_rate"] = round(account["sent"] / max(1, total_attempts) * 100, 1)
        account["success_rate"] = account["delivery_rate"]

    return list(accounts.values())


@router.get("/by-task/{task_id}")
async def stats_by_task(task_id: int, db: Session = Depends(get_db)):
    """Stats for a specific task."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return {"error": "Task not found"}

    stats = (
        db.query(MailingStats)
        .filter(MailingStats.task_id == task_id)
        .order_by(desc(MailingStats.sent_at))
        .all()
    )

    sent = sum(1 for s in stats if s.status == "sent")
    errors = sum(1 for s in stats if s.status == "error")
    bounces = sum(1 for s in stats if s.status == "bounce")
    limits = sum(1 for s in stats if s.status == "limit")
    total_attempts = sent + errors + bounces + limits
    delivery_rate = round(sent / max(1, total_attempts) * 100, 1)

    return {
        "task_id": task_id,
        "task_status": task.status,
        "total_items": task.total_items,
        "completed": task.completed_items,
        "failed": task.failed_items,
        "stats": {
            "sent": sent,
            "errors": errors,
            "bounces": bounces,
            "limits": limits,
            "total_attempts": total_attempts,
            "delivery_rate": delivery_rate,
            "success_rate": delivery_rate,
        },
        "recent": [
            {
                "account": s.account_email,
                "recipient": s.recipient_email,
                "status": s.status,
                "delivery_status": s.delivery_status,
                "tracking_token": s.tracking_token,
                "subject": s.message_subject or s.template_name,
                "error": s.error_message,
                "template": s.template_name,
                "time": s.sent_at.isoformat() if s.sent_at else None,
            }
            for s in stats[:100]
        ],
    }


@router.get("/errors")
async def recent_errors(limit: int = 50, db: Session = Depends(get_db)):
    """Recent errors for troubleshooting."""
    errors = (
        db.query(MailingStats)
        .filter(MailingStats.status.in_(["error", "bounce", "limit"]))
        .order_by(desc(MailingStats.sent_at))
        .limit(limit)
        .all()
    )

    return [
        {
            "id": e.id,
            "account": e.account_email,
            "recipient": e.recipient_email,
            "status": e.status,
            "delivery_status": e.delivery_status,
            "tracking_token": e.tracking_token,
            "subject": e.message_subject or e.template_name,
            "error": e.error_message,
            "provider": e.provider,
            "time": e.sent_at.isoformat() if e.sent_at else None,
        }
        for e in errors
    ]
