"""
Leomail v2.2 - Human Engine API Router
Auto-config, custom delays, identity generation.
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from ..services.human_engine import human_engine

router = APIRouter(prefix="/api/human-engine", tags=["human-engine"])


class AutoConfigRequest(BaseModel):
    task_type: str = "work"
    recipients_count: int = 1000
    accounts_count: int = 10


class CustomDelaysRequest(BaseModel):
    delays: dict  # {"2026-02-19": {"min": 330, "max": 360}}


@router.post("/auto-config")
async def auto_config(req: AutoConfigRequest):
    """AI-style auto-configuration of sending parameters."""
    return human_engine.auto_configure(req.task_type, req.recipients_count, req.accounts_count)


@router.post("/custom-delays")
async def set_custom_delays(req: CustomDelaysRequest):
    """Set per-day delay overrides."""
    human_engine.set_custom_delays(req.delays)
    return {"status": "ok", "days_set": len(req.delays)}


@router.get("/identity")
async def generate_identity(country: str = "us", gender: str = None):
    """Generate a test identity."""
    return human_engine.generate_identity(country, gender)
