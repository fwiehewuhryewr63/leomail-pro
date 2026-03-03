"""
Leomail v4 - Warmup Router
API endpoints for the warm-up engine.
"""
from fastapi import APIRouter, Depends, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Account, AccountStatus, Farm
from loguru import logger

router = APIRouter(prefix="/api/warmup", tags=["warmup"])


class WarmupRequest(BaseModel):
    farm_ids: list[int] = []        # Warm-up specific farms, empty = all eligible
    threads: int = 5                # Concurrent accounts
    accounts_limit: int = 0         # 0 = all eligible


class WarmupStatusResponse(BaseModel):
    running: bool = False
    accounts_processed: int = 0
    total_sent: int = 0
    total_received: int = 0
    total_errors: int = 0


# Global state
_warmup_running = False
_warmup_stats = {"accounts_processed": 0, "total_sent": 0, "total_received": 0, "total_errors": 0}
import threading
_warmup_cancel = threading.Event()


async def _run_warmup_task(farm_ids: list[int], threads: int, accounts_limit: int, db: Session):
    """Background task to run warm-up."""
    global _warmup_running, _warmup_stats
    _warmup_running = True
    _warmup_cancel.clear()
    _warmup_stats = {"accounts_processed": 0, "total_sent": 0, "total_received": 0, "total_errors": 0}

    try:
        from ..services.warmup_worker import run_warmup_batch

        # Get eligible accounts
        query = db.query(Account).filter(
            Account.status.in_([
                AccountStatus.NEW,
                AccountStatus.PHASE_1, AccountStatus.PHASE_2,
                AccountStatus.PHASE_3, AccountStatus.PHASE_4,
                AccountStatus.PHASE_5,
            ])
        )

        if farm_ids:
            query = query.filter(Account.farms.any(Farm.id.in_(farm_ids)))

        accounts = query.all()

        if accounts_limit > 0:
            accounts = accounts[:accounts_limit]

        if not accounts:
            logger.warning("[Warmup] No eligible accounts found")
            return

        logger.info(f"[Warmup] Starting warm-up for {len(accounts)} accounts, {threads} threads")

        result = await run_warmup_batch(
            accounts=accounts,
            db=db,
            cancel_event=_warmup_cancel,
            max_threads=threads,
        )

        _warmup_stats.update(result)
        logger.info(f"[Warmup] Complete: {result}")

    except Exception as e:
        logger.error(f"[Warmup] Error: {e}", exc_info=True)
    finally:
        _warmup_running = False


@router.post("/start")
async def start_warmup(request: WarmupRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Start the warm-up engine."""
    global _warmup_running
    if _warmup_running:
        return {"error": "Warmup already running", "running": True}

    background_tasks.add_task(
        _run_warmup_task,
        farm_ids=request.farm_ids,
        threads=request.threads,
        accounts_limit=request.accounts_limit,
        db=db,
    )
    return {"status": "started", "farm_ids": request.farm_ids, "threads": request.threads}


@router.post("/stop")
async def stop_warmup():
    """Stop the warm-up engine."""
    global _warmup_running
    _warmup_cancel.set()
    _warmup_running = False
    return {"status": "stopping"}


@router.get("/status")
async def warmup_status(db: Session = Depends(get_db)):
    """Get warm-up engine status + account phase distribution."""
    phase_counts = {}
    for status in [AccountStatus.NEW, AccountStatus.PHASE_1, AccountStatus.PHASE_2,
                   AccountStatus.PHASE_3, AccountStatus.PHASE_4, AccountStatus.PHASE_5,
                   AccountStatus.WARMED]:
        phase_counts[status.value] = db.query(Account).filter(Account.status == status).count()

    # Top accounts by warmup progress
    top_accounts = []
    warming = db.query(Account).filter(
        Account.status.in_([AccountStatus.PHASE_1, AccountStatus.PHASE_2,
                           AccountStatus.PHASE_3, AccountStatus.PHASE_4, AccountStatus.PHASE_5])
    ).order_by(Account.warmup_day.desc()).limit(20).all()

    for acc in warming:
        top_accounts.append({
            "id": acc.id,
            "email": acc.email,
            "provider": acc.provider,
            "status": acc.status,
            "warmup_day": acc.warmup_day or 0,
            "emails_sent_today": acc.emails_sent_today or 0,
            "total_emails_sent": acc.total_emails_sent or 0,
            "health_score": acc.health_score or 100,
        })

    return {
        "running": _warmup_running,
        "stats": _warmup_stats,
        "phases": phase_counts,
        "top_accounts": top_accounts,
    }


@router.get("/cost")
async def cost_tracking(db: Session = Depends(get_db)):
    """Cost tracking - SMS + CAPTCHA spend estimates."""
    from sqlalchemy import func

    total_accounts = db.query(Account).count()
    total_sent = db.query(func.sum(Account.total_emails_sent)).scalar() or 0

    # Estimate SMS costs (assuming ~$0.10 per SMS on average)
    gmail_accounts = db.query(Account).filter(Account.provider == "gmail").count()
    sms_cost_estimate = round(gmail_accounts * 0.10, 2)

    # Estimate CAPTCHA costs
    # FunCaptcha ~$0.003, hCaptcha ~$0.002, reCAPTCHA ~$0.003, image ~$0.001
    outlook_accounts = db.query(Account).filter(Account.provider.in_(["outlook", "hotmail"])).count()
    proton_accounts = db.query(Account).filter(Account.provider == "protonmail").count()

    captcha_cost = round(
        outlook_accounts * 0.003 +   # FunCaptcha
        proton_accounts * 0.002,     # hCaptcha
        3,
    )

    # Provider breakdown
    providers = {}
    for row in db.query(Account.provider, func.count()).group_by(Account.provider).all():
        prov = row[0] or "unknown"
        count = row[1]
        providers[prov] = {
            "count": count,
            "sms_cost": round(count * 0.10, 2) if prov == "gmail" else 0,
            "captcha_cost": round(
                count * (0.003 if prov in ("outlook", "hotmail") else
                         0.002 if prov == "protonmail" else 0), 3
            ),
        }

    return {
        "total_accounts": total_accounts,
        "total_emails_sent": total_sent,
        "estimated_costs": {
            "sms": sms_cost_estimate,
            "captcha": captcha_cost,
            "total": round(sms_cost_estimate + captcha_cost, 2),
        },
        "by_provider": providers,
    }
