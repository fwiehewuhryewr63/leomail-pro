"""
Leomail v4 — Update Router
EXE auto-update via GitHub Releases.
"""
import os
import sys
import subprocess
from fastapi import APIRouter
from loguru import logger

router = APIRouter(prefix="/api/update", tags=["update"])


@router.get("/version")
async def get_version():
    """Get current version info."""
    from ..services.updater import get_current_version, VERSION
    info = get_current_version()
    info["server_version"] = VERSION
    info["is_frozen"] = getattr(sys, 'frozen', False)
    return info


@router.get("/check")
async def check_updates():
    """Check GitHub Releases for available updates."""
    from ..services.updater import check_for_updates
    return check_for_updates()


@router.post("/download-and-apply")
async def download_and_apply():
    """
    Full update pipeline:
    1. Check for updates
    2. Backup user_data
    3. Download ZIP from GitHub Releases
    4. Extract and prepare updater.bat
    5. Launch updater.bat and exit
    """
    from ..services.updater import (
        check_for_updates, download_update, extract_and_prepare,
        backup_user_data, cleanup_old_backups
    )

    result = {
        "success": False,
        "steps": [],
        "errors": [],
    }

    # Step 1: Check for updates
    logger.info("🔄 Step 1: Checking for updates...")
    update_info = check_for_updates()
    result["steps"].append("check_complete")

    if not update_info.get("update_available"):
        result["errors"].append("No update available")
        result["current_version"] = update_info.get("current_version")
        result["remote_version"] = update_info.get("remote_version")
        return result

    download_url = update_info.get("download_url")
    if not download_url:
        result["errors"].append("No download URL in release (missing ZIP asset)")
        return result

    result["remote_version"] = update_info["remote_version"]

    # Step 2: Backup user_data
    logger.info("🔄 Step 2: Backing up user_data...")
    backup_path = backup_user_data()
    if backup_path:
        result["steps"].append("backup_complete")
        result["backup_path"] = backup_path
    cleanup_old_backups(keep_count=3)

    # Step 3: Download ZIP
    logger.info(f"🔄 Step 3: Downloading {update_info['remote_version']}...")
    dl = download_update(download_url)
    if not dl["success"]:
        result["errors"].append(f"Download failed: {dl.get('error')}")
        return result
    result["steps"].append("download_complete")

    # Step 4: Extract and prepare updater.bat
    logger.info("🔄 Step 4: Extracting and preparing updater...")
    prep = extract_and_prepare(dl["zip_path"])
    if not prep["success"]:
        result["errors"].append(f"Extract failed: {prep.get('error')}")
        return result
    result["steps"].append("extract_complete")

    # Step 5: Launch updater.bat and exit
    if getattr(sys, 'frozen', False):
        logger.info("🚀 Step 5: Launching updater.bat and exiting...")
        bat_path = prep["bat_path"]

        # Launch updater.bat detached from this process
        subprocess.Popen(
            ["cmd", "/c", bat_path],
            cwd=str(os.path.dirname(bat_path)),
            creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS,
        )
        result["steps"].append("updater_launched")
        result["success"] = True
        result["message"] = "Update downloaded. App will restart with new version."

        # Schedule exit
        import asyncio

        async def _exit():
            await asyncio.sleep(2)  # Let response be sent
            logger.info("👋 Exiting for update...")
            os._exit(0)

        asyncio.create_task(_exit())
    else:
        # Dev mode — just report ready
        result["success"] = True
        result["steps"].append("ready_dev_mode")
        result["message"] = "Update extracted. In dev mode, manually replace files."
        result["bat_path"] = prep["bat_path"]

    return result


@router.post("/restart")
async def restart_server():
    """Restart the server process."""
    import asyncio

    logger.info("🔄 Server restart requested via API")

    async def _do_restart():
        await asyncio.sleep(2)
        if getattr(sys, 'frozen', False):
            subprocess.Popen([sys.executable], cwd=os.path.dirname(sys.executable))
        else:
            subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "backend.main:app",
                 "--host", "0.0.0.0", "--port", "8000"],
                cwd=str(__import__('pathlib').Path(__file__).parent.parent.parent),
            )
        os._exit(0)

    asyncio.create_task(_do_restart())
    return {"status": "restarting", "message": "Server will restart in 2 seconds"}


@router.post("/backup")
async def manual_backup():
    """Manually trigger a user_data backup."""
    from ..services.updater import backup_user_data
    path = backup_user_data()
    if path:
        return {"status": "ok", "backup_path": path}
    return {"status": "error", "message": "Backup failed or no user_data found"}


@router.get("/backups")
async def list_backups():
    """List available backups."""
    from ..services.updater import get_app_root
    root = get_app_root()
    backups = []
    for d in sorted(root.iterdir(), reverse=True):
        if d.is_dir() and d.name.startswith("user_data_backup_"):
            db_exists = (d / "leomail.db").exists()
            size_mb = sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) / (1024 * 1024)
            backups.append({
                "name": d.name,
                "path": str(d),
                "has_db": db_exists,
                "size_mb": round(size_mb, 1),
                "created": d.stat().st_mtime,
            })
    return {"backups": backups}
