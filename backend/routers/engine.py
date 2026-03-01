"""
Leomail v4 - Engine Router
Unified API for managing all 3 engines: autoreg, warmup, campaign.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import get_db
from ..services.engine_manager import engine_manager, EngineType

router = APIRouter(prefix="/api/engine", tags=["engine"])


@router.get("/status")
def engine_status():
    """
    Get status of all 3 engines.
    Returns current state, threads, progress for autoreg/warmup/campaign.
    Frontend polls this every 2-3 seconds.
    """
    return engine_manager.get_status()


@router.get("/{engine_type}/status")
def single_engine_status(engine_type: str):
    """Get status of a single engine."""
    try:
        etype = EngineType(engine_type)
    except ValueError:
        return {"error": f"Unknown engine type: {engine_type}. Use: autoreg, warmup, campaign"}
    return engine_manager.get_engine(etype).to_dict()


@router.post("/{engine_type}/stop")
def stop_engine(engine_type: str, mode: str = "instant"):
    """
    Stop a specific engine.
    mode: "instant" = force-stop, "graceful" = finish current item
    """
    try:
        etype = EngineType(engine_type)
    except ValueError:
        return {"error": f"Unknown engine type: {engine_type}"}

    if not engine_manager.is_running(etype):
        return {"status": "not_running", "message": f"{engine_type} is not running"}

    engine_manager.stop_engine(etype, mode)

    # Also set legacy cancel flags for backward compatibility
    if etype == EngineType.AUTOREG:
        from ..routers.birth import BIRTH_CANCEL_EVENT
        BIRTH_CANCEL_EVENT.set()
    elif etype == EngineType.CAMPAIGN:
        from ..routers.work import WORK_CANCEL
        # Mark all running work task IDs for cancel
        engine = engine_manager.get_engine(etype)
        if engine.task_id:
            WORK_CANCEL.add(engine.task_id)

    return {"status": "stopping", "mode": mode}


@router.get("/running")
def running_engines():
    """List currently running engines."""
    return {"running": engine_manager.get_running_engines()}
