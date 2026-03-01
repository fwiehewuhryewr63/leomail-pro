"""
Leomail v3 - Logs Router
Real-time server logs via polling.
"""
from fastapi import APIRouter
from loguru import logger
from pathlib import Path
import os

router = APIRouter(prefix="/api/logs", tags=["logs"])

LOG_FILE = Path("user_data/logs/leomail.log")


@router.get("/")
async def get_logs(lines: int = 100, level: str = None):
    """Get last N log lines. Optional filter by level (INFO, WARNING, ERROR)."""
    if not LOG_FILE.exists():
        return {"logs": [], "total": 0}

    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()

        # Filter by level if specified
        if level:
            level = level.upper()
            all_lines = [l for l in all_lines if level in l]

        # Return last N
        result = all_lines[-lines:]
        return {
            "logs": [l.strip() for l in result],
            "total": len(all_lines)
        }
    except Exception as e:
        return {"logs": [f"Error reading logs: {e}"], "total": 0}


@router.delete("/")
async def clear_logs():
    """Clear log file."""
    if LOG_FILE.exists():
        with open(LOG_FILE, "w") as f:
            f.write("")
        logger.info("Logs cleared by user")
    return {"status": "cleared"}
