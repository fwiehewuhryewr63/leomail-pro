"""
Leomail v3 - Shared Screenshot Utility
Auto-captures debug screenshots at key flow points in all engines.
Used by warmup, work, and birth engines.
"""
import os
from datetime import datetime
from pathlib import Path
from loguru import logger

# Directory for debug screenshots
from ..database import USER_DATA_DIR as _USER_DATA_DIR
SCREENSHOT_DIR = str(_USER_DATA_DIR / "debug_screenshots")

# Global registry: thread_log_id -> {"page": Page, "context": ctx, "engine": "warmup"|"work"|"birth"}
ACTIVE_PAGES: dict[int, dict] = {}


def _ensure_dir():
    """Create screenshot directory if it doesn't exist."""
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)


async def debug_screenshot(page, label: str, account_email: str = "", engine: str = ""):
    """
    Capture a debug screenshot. Never crashes the caller.
    
    Args:
        page: Playwright page object
        label: Short label like "mail_opened", "send_error", "session_expired"
        account_email: Account email for identification
        engine: Engine name ("warmup", "work", "birth")
    
    Returns:
        Path to saved screenshot or None
    """
    try:
        _ensure_dir()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Sanitize email for filename
        safe_email = (account_email or "unknown").replace("@", "_at_").replace(".", "_")[:30]
        prefix = f"{engine}_" if engine else ""
        fname = f"{ts}_{prefix}{safe_email}_{label}.png"
        path = str(Path(SCREENSHOT_DIR) / fname)
        await page.screenshot(path=path, full_page=False)
        logger.debug(f"[SNAP] Screenshot saved: {fname}")
        return path
    except Exception as e:
        logger.debug(f"[SNAP] Screenshot failed ({label}): {e}")
        return None


def register_page(thread_log_id: int, page, context, engine: str = ""):
    """Register an active page for live screenshot access via API."""
    ACTIVE_PAGES[thread_log_id] = {"page": page, "context": context, "engine": engine}


def unregister_page(thread_log_id: int):
    """Remove page from active registry."""
    ACTIVE_PAGES.pop(thread_log_id, None)


async def live_screenshot(thread_log_id: int) -> bytes | None:
    """Take a live screenshot of an active thread's page. Returns PNG bytes or None."""
    entry = ACTIVE_PAGES.get(thread_log_id)
    if not entry or not entry.get("page"):
        return None
    try:
        return await entry["page"].screenshot(type="png")
    except Exception:
        return None
