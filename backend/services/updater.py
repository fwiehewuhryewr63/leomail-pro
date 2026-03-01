"""
Leomail v4 — Auto-update Service (EXE edition)
Checks GitHub Releases for updates, downloads ZIP, prepares updater.bat.
user_data/ is never touched — it lives outside _internal/.
"""
import os
import sys
import json
import shutil
import zipfile
import tempfile
from pathlib import Path
from datetime import datetime
from loguru import logger

# Current version
VERSION = "4.3.0"
VERSION_FILE = "version.json"

# GitHub repo for releases
GITHUB_REPO = "fwiehewuhryewr63/leomail-pro"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def get_app_root() -> Path:
    """Get application root directory (next to EXE, or project root in dev)."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent.parent


def get_current_version() -> dict:
    """Read current version info."""
    root = get_app_root()
    vfile = root / VERSION_FILE
    if vfile.exists():
        try:
            return json.loads(vfile.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "version": VERSION,
        "build_date": datetime.utcnow().isoformat(),
        "updated_at": None,
    }


def save_version_info(version: str, extra: dict = None):
    """Save version info to file."""
    root = get_app_root()
    info = {
        "version": version,
        "build_date": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    if extra:
        info.update(extra)
    (root / VERSION_FILE).write_text(json.dumps(info, indent=2), encoding="utf-8")


def check_for_updates() -> dict:
    """Check GitHub Releases for a newer version."""
    import requests
    current = get_current_version()

    try:
        resp = requests.get(GITHUB_API_URL, timeout=15, headers={
            "Accept": "application/vnd.github.v3+json",
        })
        if resp.status_code != 200:
            return {
                "current_version": current["version"],
                "remote_version": None,
                "update_available": False,
                "error": f"GitHub API returned {resp.status_code}",
            }

        data = resp.json()
        remote_version = data.get("tag_name", "").lstrip("v")
        if not remote_version:
            return {
                "current_version": current["version"],
                "remote_version": None,
                "update_available": False,
                "error": "No version tag in release",
            }

        # Compare versions (semver)
        current_parts = [int(x) for x in current["version"].split(".")]
        remote_parts = [int(x) for x in remote_version.split(".")]
        is_newer = remote_parts > current_parts

        # Find ZIP asset
        download_url = None
        download_size = 0
        for asset in data.get("assets", []):
            if asset["name"].endswith(".zip"):
                download_url = asset["browser_download_url"]
                download_size = asset.get("size", 0)
                break

        return {
            "current_version": current["version"],
            "remote_version": remote_version,
            "update_available": is_newer,
            "download_url": download_url,
            "download_size_mb": round(download_size / (1024 * 1024), 1) if download_size else 0,
            "release_name": data.get("name", ""),
            "release_notes": data.get("body", ""),
            "published_at": data.get("published_at", ""),
        }
    except Exception as e:
        logger.error(f"Update check failed: {e}")
        return {
            "current_version": current["version"],
            "remote_version": None,
            "update_available": False,
            "error": str(e),
        }


# Global progress tracker for UI updates
update_progress = {
    "active": False,
    "step": "",       # "checking", "backing_up", "downloading", "extracting", "applying", "done", "error"
    "percent": 0,
    "detail": "",
    "downloaded_mb": 0,
    "total_mb": 0,
}

def reset_progress():
    update_progress.update({"active": False, "step": "", "percent": 0, "detail": "", "downloaded_mb": 0, "total_mb": 0})

def set_progress(step: str, percent: int = 0, detail: str = ""):
    update_progress.update({"active": True, "step": step, "percent": percent, "detail": detail})


def download_update(download_url: str) -> dict:
    """
    Download update ZIP from GitHub.
    Updates global update_progress for real-time UI feedback.
    """
    import requests
    root = get_app_root()
    update_tmp = root / "_update_tmp"

    # Clean previous attempt
    if update_tmp.exists():
        shutil.rmtree(str(update_tmp), ignore_errors=True)
    update_tmp.mkdir(parents=True, exist_ok=True)

    zip_path = update_tmp / "update.zip"

    try:
        set_progress("downloading", 0, "Connecting...")
        logger.info(f"⬇️ Downloading update from {download_url}...")
        resp = requests.get(download_url, stream=True, timeout=300)
        resp.raise_for_status()

        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        total_mb = round(total / (1024 * 1024), 1) if total else 0
        update_progress["total_mb"] = total_mb

        with open(zip_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
                downloaded += len(chunk)
                dl_mb = round(downloaded / (1024 * 1024), 1)
                pct = int(downloaded / total * 100) if total else 0
                update_progress["downloaded_mb"] = dl_mb
                update_progress["percent"] = pct
                update_progress["detail"] = f"{dl_mb} / {total_mb} MB"

        logger.info(f"✅ Downloaded {downloaded / (1024*1024):.1f} MB")
        return {"success": True, "zip_path": str(zip_path)}

    except Exception as e:
        logger.error(f"Download failed: {e}")
        set_progress("error", 0, f"Download failed: {e}")
        return {"success": False, "error": str(e)}


def extract_and_prepare(zip_path: str) -> dict:
    """
    Extract downloaded ZIP and prepare updater.bat.
    ZIP should contain Leomail/ folder with Leomail.exe + _internal/.
    """
    set_progress("extracting", 80, "Extracting update...")
    root = get_app_root()
    update_tmp = root / "_update_tmp"
    extract_dir = update_tmp / "extracted"

    try:
        # Extract ZIP
        logger.info("📦 Extracting update...")
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(str(extract_dir))

        # Find Leomail.exe in extracted content
        exe_found = None
        for p in extract_dir.rglob("Leomail.exe"):
            exe_found = p.parent
            break

        if not exe_found:
            return {"success": False, "error": "Leomail.exe not found in ZIP"}

        # Verify _internal/ exists
        internal_dir = exe_found / "_internal"
        if not internal_dir.exists():
            return {"success": False, "error": "_internal/ not found in ZIP"}

        logger.info(f"✅ Found update in: {exe_found}")

        # Generate updater.bat
        # Uses relative paths from EXE directory
        exe_rel = exe_found.relative_to(root) if exe_found.is_relative_to(root) else exe_found
        bat_content = f"""@echo off
chcp 65001 >nul
echo ══════════════════════════════════════════
echo   Leomail Auto-Updater
echo ══════════════════════════════════════════
echo.
echo Waiting for Leomail.exe to close...

:wait_loop
tasklist /FI "IMAGENAME eq Leomail.exe" 2>nul | find /i "Leomail.exe" >nul
if %errorlevel%==0 (
    timeout /t 1 /nobreak >nul
    goto wait_loop
)

echo Leomail.exe closed. Applying update...

:: Backup current EXE (just in case)
if exist "Leomail.exe.bak" del /f "Leomail.exe.bak"
if exist "Leomail.exe" rename "Leomail.exe" "Leomail.exe.bak"

:: Remove old _internal
if exist "_internal" rmdir /s /q "_internal"

:: Copy new files
echo Copying new _internal...
xcopy /e /y /q "{exe_rel}\\_internal" "_internal\\" >nul
echo Copying new Leomail.exe...
copy /y "{exe_rel}\\Leomail.exe" "Leomail.exe" >nul

:: Copy version.json if exists
if exist "{exe_rel}\\version.json" copy /y "{exe_rel}\\version.json" "version.json" >nul

:: Cleanup
echo Cleaning up...
if exist "_update_tmp" rmdir /s /q "_update_tmp"
if exist "Leomail.exe.bak" del /f "Leomail.exe.bak"

echo.
echo ══════════════════════════════════════════
echo   Update complete! Starting Leomail...
echo ══════════════════════════════════════════
timeout /t 2 /nobreak >nul

:: Start new version
start "" "Leomail.exe"

:: Self-delete this bat
(goto) 2>nul & del "%~f0"
"""
        bat_path = root / "_updater.bat"
        bat_path.write_text(bat_content, encoding="utf-8")
        logger.info(f"✅ Updater script ready: {bat_path}")

        return {"success": True, "bat_path": str(bat_path)}

    except Exception as e:
        logger.error(f"Extract failed: {e}")
        return {"success": False, "error": str(e)}


def backup_user_data() -> str | None:
    """Backup user_data directory. Returns backup path."""
    root = get_app_root()
    user_data = root / "user_data"

    if not user_data.exists():
        logger.info("No user_data to backup")
        return None

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_dir = root / f"user_data_backup_{timestamp}"

    try:
        shutil.copytree(str(user_data), str(backup_dir))
        logger.info(f"✅ user_data backed up to {backup_dir}")

        db_path = backup_dir / "leomail.db"
        if db_path.exists():
            logger.info(f"   leomail.db size: {db_path.stat().st_size} bytes")
        else:
            logger.warning("   ⚠️ leomail.db NOT in backup!")

        return str(backup_dir)
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        return None


def cleanup_old_backups(keep_count: int = 3):
    """Remove old backup directories, keeping only the last N."""
    root = get_app_root()
    backups = sorted(
        [d for d in root.iterdir() if d.is_dir() and d.name.startswith("user_data_backup_")],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    for old_backup in backups[keep_count:]:
        try:
            shutil.rmtree(str(old_backup))
            logger.info(f"Cleaned up old backup: {old_backup.name}")
        except Exception:
            pass
