"""
Leomail v4 - Auto-update Service (EXE edition)
Checks GitHub Releases for updates, downloads ZIP, prepares updater.bat.
user_data/ is never touched - it lives outside _internal/.
"""
import os
import sys
import json
import shutil
import sqlite3
import zipfile
import tempfile
from pathlib import Path
from datetime import datetime
from loguru import logger

# Current version - read from version.json at import time
VERSION_FILE = "version.json"
UPDATE_RESULT_FILE = "_update_result.txt"

def _read_version_from_file() -> str:
    """Read version from version.json, checking multiple possible locations."""
    candidates = []
    # 1. Frozen EXE: next to Leomail.exe
    if getattr(sys, 'frozen', False):
        candidates.append(Path(sys.executable).parent / VERSION_FILE)
        candidates.append(Path(sys._MEIPASS) / VERSION_FILE)
    # 2. Dev mode: source/version.json
    candidates.append(Path(__file__).parent.parent.parent / VERSION_FILE)
    candidates.append(Path(__file__).parent.parent / VERSION_FILE)

    for vpath in candidates:
        if vpath.exists():
            try:
                data = json.loads(vpath.read_text(encoding="utf-8"))
                return data.get("version", "0.0.0")
            except Exception:
                continue
    return "0.0.0"

VERSION = _read_version_from_file()
_LAST_BACKUP_ERROR = ""

# GitHub repo for releases
GITHUB_REPO = "fwiehewuhryewr63/leomail-pro"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def get_app_root() -> Path:
    """Get application root directory (next to EXE, or project root in dev)."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent.parent


def get_update_result_path() -> Path:
    """Marker file used to report the last update/rollback result after restart."""
    return get_app_root() / UPDATE_RESULT_FILE


def get_last_backup_error() -> str:
    return _LAST_BACKUP_ERROR


def _set_last_backup_error(message: str = ""):
    global _LAST_BACKUP_ERROR
    _LAST_BACKUP_ERROR = message


def read_and_clear_update_result() -> dict:
    """Read one-shot update result marker and remove it."""
    path = get_update_result_path()
    if not path.exists():
        return {"status": None}

    data = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                data[key.strip()] = value.strip()
    except Exception as e:
        logger.warning(f"[Update] Failed to read update result marker: {e}")
    finally:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass

    return {
        "status": data.get("status"),
        "detail": data.get("detail", ""),
        "at": data.get("at", ""),
    }


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


def _backup_sqlite_snapshot(src: Path, dst: Path) -> bool:
    """Create a consistent SQLite snapshot for live user_data backups."""
    if not src.exists():
        return False
    src_conn = None
    dst_conn = None
    try:
        src_conn = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=30)
        dst_conn = sqlite3.connect(str(dst), timeout=30)
        src_conn.backup(dst_conn)
        return True
    except Exception as e:
        logger.error(f"[Backup] SQLite snapshot failed: {e}")
        try:
            dst.unlink(missing_ok=True)
        except Exception:
            pass


def _safe_copy_for_backup(src: str, dst: str, *, follow_symlinks: bool = True):
    """
    Best-effort file copy for live user_data backups.
    Chrome profile files can be locked while the app is running; those should
    not abort the whole safety backup when the DB snapshot is preserved
    separately.
    """
    try:
        return shutil.copy2(src, dst, follow_symlinks=follow_symlinks)
    except OSError as e:
        msg = str(e).lower()
        if getattr(e, "winerror", None) == 32 or "being used by another process" in msg:
            logger.warning(f"[Backup] Skipping locked file during backup: {src}")
            return dst
        raise
        return False
    finally:
        try:
            if dst_conn:
                dst_conn.close()
        except Exception:
            pass
        try:
            if src_conn:
                src_conn.close()
        except Exception:
            pass


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

        # Compare versions (semver, ignoring non-numeric suffixes like .new, .beta)
        import re
        def parse_ver(v):
            return [int(x) for x in re.findall(r'\d+', v)][:3]
        current_parts = parse_ver(current["version"])
        remote_parts = parse_ver(remote_version)
        is_newer = remote_parts > current_parts

        # Find ZIP asset
        download_url = None
        download_size = 0
        for asset in data.get("assets", []):
            if asset["name"].endswith(".zip"):
                download_url = asset["browser_download_url"]
                download_size = asset.get("size", 0)
                break

        # Parse optional SHA-256 from release body (e.g. "sha256: abc123...")
        sha256_match = re.search(r'sha256:\s*([a-fA-F0-9]{64})', data.get("body", "") or "")
        expected_sha256 = sha256_match.group(1).lower() if sha256_match else None

        return {
            "current_version": current["version"],
            "remote_version": remote_version,
            "update_available": is_newer,
            "download_url": download_url,
            "download_size_mb": round(download_size / (1024 * 1024), 1) if download_size else 0,
            "release_name": data.get("name", ""),
            "release_notes": data.get("body", ""),
            "published_at": data.get("published_at", ""),
            "expected_sha256": expected_sha256,
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


def download_update(download_url: str, expected_sha256: str = None) -> dict:
    """
    Download update ZIP from GitHub.
    Updates global update_progress for real-time UI feedback.
    Optionally verifies SHA-256 if expected_sha256 is provided.
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
        logger.info(f"[Update] Downloading from {download_url}...")
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

        logger.info(f"[Update] Downloaded {downloaded / (1024*1024):.1f} MB")

        # Verify download completeness against content-length when present
        if total > 0 and downloaded != total:
            logger.error(f"[Update] Size mismatch: got {downloaded} bytes, expected {total}")
            set_progress("error", 0, f"Download incomplete: {downloaded}/{total} bytes")
            # Remove truncated/bad ZIP and staging dir before returning
            try:
                zip_path.unlink(missing_ok=True)
            except Exception:
                pass
            try:
                shutil.rmtree(str(update_tmp), ignore_errors=True)
            except Exception:
                pass
            return {"success": False, "error": f"Download incomplete: got {downloaded} of {total} bytes"}

        # Verify SHA-256 when expected hash is provided
        if expected_sha256:
            import hashlib
            set_progress("verifying", 92, "Verifying SHA-256...")
            actual_sha256 = hashlib.sha256(zip_path.read_bytes()).hexdigest()
            if actual_sha256 != expected_sha256:
                logger.error(f"[Update] SHA-256 mismatch: {actual_sha256} != {expected_sha256}")
                set_progress("error", 0, "SHA-256 verification failed")
                try:
                    zip_path.unlink(missing_ok=True)
                except Exception:
                    pass
                try:
                    shutil.rmtree(str(update_tmp), ignore_errors=True)
                except Exception:
                    pass
                return {"success": False, "error": "SHA-256 verification failed — download may be corrupted"}
            logger.info(f"[Update] SHA-256 verified: {actual_sha256[:16]}...")

        return {"success": True, "zip_path": str(zip_path)}

    except Exception as e:
        logger.error(f"Download failed: {e}")
        set_progress("error", 0, f"Download failed: {e}")
        return {"success": False, "error": str(e)}


def extract_and_prepare(zip_path: str) -> dict:
    """
    Extract downloaded ZIP and prepare updater.bat.
    ZIP should contain Leomail/ folder with Leomail.exe + _internal/.
    Uses rollback-safe atomic swap pattern.
    """
    set_progress("extracting", 80, "Extracting update...")
    root = get_app_root()
    update_tmp = root / "_update_tmp"
    extract_dir = update_tmp / "extracted"

    try:
        # Extract ZIP
        logger.info("[Update] Extracting update...")
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

        logger.info(f"[Update] Found update in: {exe_found}")

        # Generate updater.bat with rollback-safe atomic swap
        exe_rel = exe_found.relative_to(root) if exe_found.is_relative_to(root) else exe_found
        src = str(exe_rel)
        bat_lines = [
            '@echo off',
            'setlocal EnableExtensions EnableDelayedExpansion',
            'chcp 65001 >nul',
            'echo ==========================================',
            'echo   Leomail Auto-Updater',
            'echo ==========================================',
            'echo.',
            'echo Waiting for Leomail.exe to close...',
            '',
            'set WAIT_SECS=0',
            ':wait_loop',
            'tasklist /FI "IMAGENAME eq Leomail.exe" 2>nul | find /i "Leomail.exe" >nul',
            'if %errorlevel%==0 (',
            '    if !WAIT_SECS! GEQ 15 goto force_close',
            '    set /a WAIT_SECS+=1',
            '    timeout /t 1 /nobreak >nul',
            '    goto wait_loop',
            ')',
            '',
            'goto apply_update',
            '',
            ':force_close',
            'echo Leomail.exe did not exit in time. Force-closing lingering runtime...',
            'taskkill /f /im "Leomail.exe" /t >nul 2>&1',
            'timeout /t 2 /nobreak >nul',
            '',
            ':apply_update',
            'echo Leomail.exe closed. Applying update...',
            '',
            f'if exist "{UPDATE_RESULT_FILE}" del /f "{UPDATE_RESULT_FILE}"',
            '',
            ':: Phase 1: Rename current runtime aside (recoverable)',
            'echo [1/4] Backing up current version...',
            'if exist "Leomail.exe.bak" del /f "Leomail.exe.bak"',
            'if exist "_internal.old" rmdir /s /q "_internal.old"',
            'if exist "Leomail.exe" rename "Leomail.exe" "Leomail.exe.bak"',
            'if exist "_internal" rename "_internal" "_internal.old"',
            '',
            ':: Phase 2: Copy new files (with error checking)',
            'echo [2/4] Installing new version...',
            f'xcopy /e /y /q "{src}\\_internal" "_internal\\" >nul',
            'if errorlevel 1 goto :rollback',
            f'copy /y "{src}\\Leomail.exe" "Leomail.exe" >nul',
            'if errorlevel 1 goto :rollback',
            f'if exist "{src}\\version.json" copy /y "{src}\\version.json" "version.json" >nul',
            '',
            ':: Phase 3: Verify new files exist',
            'echo [3/4] Verifying update...',
            'if not exist "Leomail.exe" goto :rollback',
            'if not exist "_internal" goto :rollback',
            '',
            ':: Phase 4: Success - cleanup staging, keep .old/.bak as safety net',
            'echo [4/4] Cleaning up...',
            'if exist "_update_tmp" rmdir /s /q "_update_tmp"',
            'echo NOTE: _internal.old and Leomail.exe.bak kept until next update.',
            'echo They will be auto-cleaned on next successful update.', 
            '',
            ':: Clear Chromium UI cache (correct path)',
            'if exist "user_data\\chromium_profile\\Cache" rmdir /s /q "user_data\\chromium_profile\\Cache"',
            'if exist "user_data\\chromium_profile\\Code Cache" rmdir /s /q "user_data\\chromium_profile\\Code Cache"',
            '',
            'echo.',
            'echo ==========================================',
            'echo   Update complete! Starting Leomail...',
            'echo ==========================================',
            f'> "{UPDATE_RESULT_FILE}" echo status=success',
            f'>> "{UPDATE_RESULT_FILE}" echo detail=runtime_updated',
            f'>> "{UPDATE_RESULT_FILE}" echo at=%date% %time%',
            'timeout /t 2 /nobreak >nul',
            'start "" "Leomail.exe"',
            '(goto) 2>nul & del "%~f0"',
            '',
            ':: Rollback: restore previous version on failure',
            ':rollback',
            'echo.',
            'echo !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!',
            'echo   UPDATE FAILED - Rolling back...',
            'echo !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!',
            '',
            ':: Force-remove any broken/partial new files',
            'if exist "Leomail.exe" del /f "Leomail.exe"',
            'if exist "_internal" rmdir /s /q "_internal"',
            '',
            ':: Restore previous known-good runtime',
            'if exist "Leomail.exe.bak" rename "Leomail.exe.bak" "Leomail.exe"',
            'if exist "_internal.old" rename "_internal.old" "_internal"', 
            '',
            'echo Update failed at %date% %time% > "_update_failed.log"',
            'echo Previous version preserved. Recovery from .bak/.old files. >> "_update_failed.log"',
            f'> "{UPDATE_RESULT_FILE}" echo status=rollback',
            f'>> "{UPDATE_RESULT_FILE}" echo detail=previous_version_restored',
            f'>> "{UPDATE_RESULT_FILE}" echo at=%date% %time%',
            '',
            'echo.',
            'echo Previous version has been restored.',
            'echo Starting Leomail in 3 seconds...',
            'echo.',
            'timeout /t 3 /nobreak >nul',
            'if exist "Leomail.exe" start "" "Leomail.exe"',
            '(goto) 2>nul & del "%~f0"',
        ]
        bat_content = '\r\n'.join(bat_lines) + '\r\n'
        bat_path = root / "_updater.bat"
        bat_path.write_text(bat_content, encoding="utf-8")
        logger.info(f"[Update] Updater script ready: {bat_path}")

        return {"success": True, "bat_path": str(bat_path)}

    except Exception as e:
        logger.error(f"Extract failed: {e}")
        return {"success": False, "error": str(e)}


def backup_user_data() -> str | None:
    """Backup user_data directory with a consistent SQLite snapshot for leomail.db."""
    root = get_app_root()
    user_data = root / "user_data"
    _set_last_backup_error("")

    if not user_data.exists():
        logger.info("No user_data to backup")
        _set_last_backup_error("user_data directory not found")
        return None

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_dir = root / f"user_data_backup_{timestamp}"
    db_src = user_data / "leomail.db"
    db_dst = backup_dir / "leomail.db"

    try:
        shutil.copytree(
            str(user_data),
            str(backup_dir),
            ignore=shutil.ignore_patterns("leomail.db", "leomail.db-wal", "leomail.db-shm"),
            copy_function=_safe_copy_for_backup,
        )
        if db_src.exists() and not _backup_sqlite_snapshot(db_src, db_dst):
            shutil.rmtree(str(backup_dir), ignore_errors=True)
            _set_last_backup_error("SQLite snapshot backup failed")
            return None
        logger.info(f"[Backup] user_data backed up to {backup_dir}")

        if db_dst.exists():
            logger.info(f"   leomail.db size: {db_dst.stat().st_size} bytes")
        else:
            logger.warning("   [WARN] leomail.db NOT in backup!")

        return str(backup_dir)
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        _set_last_backup_error(str(e))
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
