"""
Leomail v2.2 - Error Handler API Router
Error statistics and ban/bounce monitoring endpoints.
"""
from fastapi import APIRouter
from ..services.error_handler import error_handler

router = APIRouter(prefix="/api/errors", tags=["errors"])


@router.get("/stats")
async def error_stats():
    """Get error statistics for dashboard."""
    return error_handler.get_stats()


@router.get("/bounce-rate/{email}")
async def bounce_rate(email: str):
    """Get bounce rate for a specific account."""
    rate = error_handler.get_bounce_rate(email)
    return {
        "email": email,
        "bounce_rate": round(rate * 100, 2),
        "sent": error_handler.account_sent.get(email, 0),
        "bounces": error_handler.account_bounces.get(email, 0),
    }
