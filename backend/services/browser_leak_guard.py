"""
Browser Leak Guard - detects and kills orphaned Chromium/Playwright processes.
Prevents memory leaks from browser processes that survive after tasks complete.
IMPORTANT: Never kills the main Leomail UI window or its child processes.
"""
import os
import time
from loguru import logger

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    logger.warning("psutil not installed - browser leak guard disabled")


# Process names to look for (Playwright uses these)
BROWSER_PROCESS_NAMES = {
    "chromium", "chrome", "msedge", "firefox",
    "playwright", "node",
}

# Keywords that indicate Playwright-spawned birth/task processes (NOT the UI)
PLAYWRIGHT_CMDLINE_MARKERS = [
    "playwright", "--remote-debugging", "--headless",
    "--disable-blink-features",
]

# Keywords that indicate this is the main UI window or its child processes
# These processes must NEVER be killed
UI_PROTECTION_MARKERS = [
    "--app=",
    "chromium_profile",  # user-data-dir for the UI window
]


def _is_ui_process(cmdline: str) -> bool:
    """Check if a chrome process belongs to the main Leomail UI window."""
    return any(marker in cmdline for marker in UI_PROTECTION_MARKERS)


def _is_playwright_task_process(cmdline: str) -> bool:
    """Check if a chrome process was spawned by Playwright for birth/warmup tasks."""
    if "browser_profiles" in cmdline:
        return True
    return any(marker in cmdline for marker in PLAYWRIGHT_CMDLINE_MARKERS)


def get_orphaned_browser_pids(max_age_seconds: int = 300) -> list[int]:
    """
    Find browser processes that have been running longer than max_age_seconds.
    Only returns PIDs of Playwright task processes - NEVER UI processes.
    """
    if not HAS_PSUTIL:
        return []

    orphans = []
    now = time.time()

    for proc in psutil.process_iter(["pid", "name", "create_time", "cmdline"]):
        try:
            name = (proc.info["name"] or "").lower()
            pid = proc.info["pid"]
            create_time = proc.info["create_time"]

            # Skip if process is too young
            age = now - create_time
            if age < max_age_seconds:
                continue

            # Check if it's a browser process
            is_browser = any(bn in name for bn in BROWSER_PROCESS_NAMES)
            if not is_browser:
                continue

            # Get command line
            cmdline = " ".join(proc.info.get("cmdline") or []).lower()

            # NEVER kill UI processes (main window + its renderers/GPU/etc)
            if _is_ui_process(cmdline):
                continue

            # Only kill processes that are clearly Playwright task processes
            if _is_playwright_task_process(cmdline):
                orphans.append(pid)

        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    return orphans


def kill_orphaned_browsers(max_age_seconds: int = 300) -> int:
    """
    Kill orphaned browser processes older than max_age_seconds.
    Returns number of processes killed.
    """
    if not HAS_PSUTIL:
        return 0

    orphans = get_orphaned_browser_pids(max_age_seconds)
    killed = 0

    for pid in orphans:
        try:
            proc = psutil.Process(pid)
            proc_name = proc.name()
            proc.terminate()
            # Give it 3 seconds to terminate gracefully
            try:
                proc.wait(timeout=3)
            except psutil.TimeoutExpired:
                proc.kill()  # Force kill
            killed += 1
            logger.info(f"[LeakGuard] Killed orphaned process: {proc_name} (PID {pid})")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if killed:
        logger.info(f"[LeakGuard] Cleaned up {killed} orphaned browser processes")

    return killed


def get_browser_memory_usage_mb() -> float:
    """Get total memory usage of all browser-related processes in MB."""
    if not HAS_PSUTIL:
        return 0.0

    total_bytes = 0
    for proc in psutil.process_iter(["name", "memory_info", "cmdline"]):
        try:
            name = (proc.info["name"] or "").lower()
            is_browser = any(bn in name for bn in BROWSER_PROCESS_NAMES)
            if is_browser:
                cmdline = " ".join(proc.info.get("cmdline") or []).lower()
                # Only count Playwright task processes, not the UI
                if _is_playwright_task_process(cmdline) and not _is_ui_process(cmdline):
                    total_bytes += proc.info["memory_info"].rss
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    return total_bytes / (1024 * 1024)


async def periodic_leak_guard(interval_seconds: int = 120, max_age_seconds: int = 300):
    """
    Background coroutine that periodically checks for and kills orphaned browsers.
    Run as asyncio.create_task(periodic_leak_guard()) on startup.
    """
    import asyncio
    logger.info(f"[LeakGuard] Started - checking every {interval_seconds}s for processes older than {max_age_seconds}s")

    while True:
        try:
            await asyncio.sleep(interval_seconds)
            killed = kill_orphaned_browsers(max_age_seconds)
            if killed:
                mem_mb = get_browser_memory_usage_mb()
                logger.info(f"[LeakGuard] Remaining browser memory: {mem_mb:.0f} MB")
        except Exception as e:
            logger.debug(f"[LeakGuard] Error: {e}")
