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
import subprocess
import zipfile
import tempfile
import re
from pathlib import Path
from datetime import datetime
from loguru import logger

# Current version - read from version.json at import time
VERSION_FILE = "version.json"
UPDATE_RESULT_FILE = "_update_result.txt"
UPDATE_STARTED_FILE = "_update_started.txt"
UPDATE_LAUNCH_FILE = "_update_launch.txt"
UPDATE_FAILED_LOG = "_update_failed.log"
UPDATE_PHASE_FILE = "_update_phase.txt"
UPDATER_SCRIPT_FILE = "_updater.ps1"

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


def _parse_version_tuple(version: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", version or "")
    if not parts:
        return (0,)
    return tuple(int(part) for part in parts[:4])


def _read_staged_update_version(root: Path) -> str:
    staged_root = root / "_update_tmp" / "extracted"
    if not staged_root.exists():
        return "0.0.0"
    for vpath in staged_root.rglob(VERSION_FILE):
        try:
            data = json.loads(vpath.read_text(encoding="utf-8"))
            version = data.get("version", "0.0.0")
            if version and version != "0.0.0":
                return version
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


def get_update_started_path() -> Path:
    return get_app_root() / UPDATE_STARTED_FILE


def get_update_launch_path() -> Path:
    return get_app_root() / UPDATE_LAUNCH_FILE


def cleanup_preexisting_update_state() -> dict:
    """
    A fresh update attempt must not inherit stale staged files or handoff
    markers from an interrupted older cycle.
    """
    root = get_app_root()
    current_version = get_current_version().get("version", "0.0.0")
    staged_version = _read_staged_update_version(root)
    cleaned: list[str] = []

    def remove_path(path: Path, label: str):
        try:
            if path.is_dir():
                if path.exists():
                    shutil.rmtree(str(path), ignore_errors=True)
                    cleaned.append(label)
            elif path.exists():
                path.unlink(missing_ok=True)
                cleaned.append(label)
        except Exception as e:
            logger.warning(f"[Update] Failed to remove stale {label}: {e}")

    remove_path(root / "_update_tmp", "_update_tmp")
    remove_path(root / "_updater.bat", "_updater.bat")
    remove_path(root / UPDATER_SCRIPT_FILE, UPDATER_SCRIPT_FILE)
    remove_path(root / UPDATE_STARTED_FILE, UPDATE_STARTED_FILE)
    remove_path(root / UPDATE_LAUNCH_FILE, UPDATE_LAUNCH_FILE)
    remove_path(root / UPDATE_FAILED_LOG, UPDATE_FAILED_LOG)
    remove_path(root / UPDATE_PHASE_FILE, UPDATE_PHASE_FILE)

    if cleaned:
        logger.info(
            "[Update] Cleared stale update state before new cycle "
            f"(current={current_version}, staged={staged_version}): {', '.join(cleaned)}"
        )
    return {"cleaned": cleaned, "current_version": current_version, "staged_version": staged_version}


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


def mark_updater_launch(status: str, detail: str = ""):
    """Write a small marker so live VPS debugging can tell whether launch handoff happened."""
    path = get_update_launch_path()
    try:
        path.write_text(
            "\n".join([
                f"status={status}",
                f"detail={detail}",
                f"at={datetime.utcnow().isoformat()}",
            ]) + "\n",
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning(f"[Update] Failed to write update launch marker: {e}")


def launch_updater_detached(script_path: str) -> dict:
    """
    Launch updater script in a way that survives the parent windowed EXE process.
    Require an early started-marker acknowledgement so the caller does not
    report "restarting" when the batch never actually began.
    """
    script_path = str(Path(script_path))
    workdir = str(Path(script_path).parent)
    started_path = get_update_started_path()
    try:
        started_path.unlink(missing_ok=True)
    except Exception:
        pass
    mark_updater_launch("dispatching", script_path)
    try:
        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-WindowStyle",
                "Hidden",
                "-File",
                script_path,
            ],
            cwd=workdir,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        for _ in range(20):
            if started_path.exists():
                mark_updater_launch("started_ack", script_path)
                return {"success": True}
            import time
            time.sleep(0.1)
        mark_updater_launch("start_not_acknowledged", script_path)
        return {"success": False, "error": "Updater script did not acknowledge start"}
    except Exception as primary_error:
        logger.error(f"[Update] Detached updater launch failed: {primary_error}")
        mark_updater_launch("launch_failed", str(primary_error))
        return {"success": False, "error": str(primary_error)}


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


def extract_and_prepare(zip_path: str, current_pid: int | None = None) -> dict:
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

        # Generate updater.ps1 with rollback-safe atomic swap
        exe_rel = exe_found.relative_to(root) if exe_found.is_relative_to(root) else exe_found
        src = str(exe_rel).replace("\\", "\\\\")
        script_lines = [
            "$ErrorActionPreference = 'Stop'",
            "$root = Split-Path -Parent $MyInvocation.MyCommand.Path",
            "Set-Location $root",
            f"$TargetPid = {current_pid or 0}",
            f"$StartedPath = Join-Path $root '{UPDATE_STARTED_FILE}'",
            f"$LaunchPath = Join-Path $root '{UPDATE_LAUNCH_FILE}'",
            f"$ResultPath = Join-Path $root '{UPDATE_RESULT_FILE}'",
            f"$FailedPath = Join-Path $root '{UPDATE_FAILED_LOG}'",
            f"$PhasePath = Join-Path $root '{UPDATE_PHASE_FILE}'",
            f"$NewRoot = Join-Path $root '{src}'",
            "$ExeBak = Join-Path $root 'Leomail.exe.bak'",
            "$InternalOld = Join-Path $root '_internal.old'",
            "$LiveExe = Join-Path $root 'Leomail.exe'",
            "$LiveInternal = Join-Path $root '_internal'",
            "$NewExe = Join-Path $NewRoot 'Leomail.exe'",
            "$NewInternal = Join-Path $NewRoot '_internal'",
            "$NewVersion = Join-Path $NewRoot 'version.json'",
            "",
            "function Write-Phase([string]$phase, [string[]]$extra = @()) {",
            "  $lines = @(",
            "    \"phase=$phase\",",
            "    \"pid=$TargetPid\",",
            "    \"at=$([DateTime]::Now.ToString('s'))\"",
            "  )",
            "  if ($extra) { $lines += $extra }",
            "  Set-Content -Path $PhasePath -Value $lines -Encoding UTF8",
            "}",
            "",
            "function Remove-Markers() {",
            "  Remove-Item $StartedPath -Force -ErrorAction SilentlyContinue",
            "  Remove-Item $LaunchPath -Force -ErrorAction SilentlyContinue",
            "}",
            "",
            "Set-Content -Path $StartedPath -Value @(",
            "  'status=started',",
            "  \"pid=$TargetPid\",",
            "  \"at=$([DateTime]::Now.ToString('s'))\"",
            ") -Encoding UTF8",
            "Write-Phase 'waiting_for_exit'",
            "",
            "$deadline = (Get-Date).AddSeconds(5)",
            "while ((Get-Date) -lt $deadline) {",
            "  $proc = if ($TargetPid -ne 0) { Get-Process -Id $TargetPid -ErrorAction SilentlyContinue } else { Get-Process Leomail -ErrorAction SilentlyContinue }",
            "  if (-not $proc) { break }",
            "  Start-Sleep -Seconds 1",
            "}",
            "",
            "$proc = if ($TargetPid -ne 0) { Get-Process -Id $TargetPid -ErrorAction SilentlyContinue } else { Get-Process Leomail -ErrorAction SilentlyContinue }",
            "if ($proc) {",
            "  Write-Phase 'force_close'",
            "  if ($TargetPid -ne 0) { Stop-Process -Id $TargetPid -Force -ErrorAction SilentlyContinue }",
            "  Get-Process Leomail -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue",
            "  $deadline = (Get-Date).AddSeconds(10)",
            "  while ((Get-Date) -lt $deadline) {",
            "    $proc = if ($TargetPid -ne 0) { Get-Process -Id $TargetPid -ErrorAction SilentlyContinue } else { Get-Process Leomail -ErrorAction SilentlyContinue }",
            "    if (-not $proc) { break }",
            "    Start-Sleep -Seconds 1",
            "  }",
            "  $proc = if ($TargetPid -ne 0) { Get-Process -Id $TargetPid -ErrorAction SilentlyContinue } else { Get-Process Leomail -ErrorAction SilentlyContinue }",
            "  if ($proc) {",
            "    Write-Phase 'runtime_still_alive'",
            "    Set-Content -Path $FailedPath -Value @(",
            "      \"Update failed at $([DateTime]::Now.ToString('s'))\",",
            "      'Runtime did not terminate after forced close attempt.'",
            "    ) -Encoding UTF8",
            "    Set-Content -Path $ResultPath -Value @(",
            "      'status=failed',",
            "      'detail=runtime_did_not_exit',",
            "      \"at=$([DateTime]::Now.ToString('s'))\"",
            "    ) -Encoding UTF8",
            "    Remove-Markers",
            "    exit 1",
            "  }",
            "}",
            "",
            "Write-Phase 'apply_update'",
            "Remove-Item $ResultPath -Force -ErrorAction SilentlyContinue",
            "Remove-Item $FailedPath -Force -ErrorAction SilentlyContinue",
            "",
            "try {",
            "  Remove-Item $ExeBak -Force -ErrorAction SilentlyContinue",
            "  Remove-Item $InternalOld -Recurse -Force -ErrorAction SilentlyContinue",
            "  if (Test-Path $LiveExe) { Move-Item $LiveExe $ExeBak -Force }",
            "  if (Test-Path $LiveInternal) { Move-Item $LiveInternal $InternalOld -Force }",
            "",
            "  Copy-Item $NewInternal $LiveInternal -Recurse -Force",
            "  Copy-Item $NewExe $LiveExe -Force",
            "  if (Test-Path $NewVersion) { Copy-Item $NewVersion (Join-Path $root 'version.json') -Force }",
            "",
            "  if (-not (Test-Path $LiveExe)) { throw 'Leomail.exe missing after copy' }",
            "  if (-not (Test-Path $LiveInternal)) { throw '_internal missing after copy' }",
            "",
            "  Remove-Item (Join-Path $root '_update_tmp') -Recurse -Force -ErrorAction SilentlyContinue",
            "  Remove-Item (Join-Path $root 'user_data\\chromium_profile\\Cache') -Recurse -Force -ErrorAction SilentlyContinue",
            "  Remove-Item (Join-Path $root 'user_data\\chromium_profile\\Code Cache') -Recurse -Force -ErrorAction SilentlyContinue",
            "",
            "  Write-Phase 'success'",
            "  Set-Content -Path $ResultPath -Value @(",
            "    'status=success',",
            "    'detail=runtime_updated',",
            "    \"at=$([DateTime]::Now.ToString('s'))\"",
            "  ) -Encoding UTF8",
            "  Remove-Markers",
            "  Start-Sleep -Seconds 2",
            "  Start-Process $LiveExe",
            "  exit 0",
            "} catch {",
            "  Remove-Item $LiveExe -Force -ErrorAction SilentlyContinue",
            "  Remove-Item $LiveInternal -Recurse -Force -ErrorAction SilentlyContinue",
            "  if (Test-Path $ExeBak) { Move-Item $ExeBak $LiveExe -Force }",
            "  if (Test-Path $InternalOld) { Move-Item $InternalOld $LiveInternal -Force }",
            "  Write-Phase 'rollback'",
            "  Set-Content -Path $FailedPath -Value @(",
            "    \"Update failed at $([DateTime]::Now.ToString('s'))\",",
            "    ('Rollback triggered: ' + $_.Exception.Message)",
            "  ) -Encoding UTF8",
            "  Set-Content -Path $ResultPath -Value @(",
            "    'status=rollback',",
            "    'detail=previous_version_restored',",
            "    \"at=$([DateTime]::Now.ToString('s'))\"",
            "  ) -Encoding UTF8",
            "  Remove-Markers",
            "  Start-Sleep -Seconds 3",
            "  if (Test-Path $LiveExe) { Start-Process $LiveExe }",
            "  exit 1",
            "}",
        ]
        script_content = '\r\n'.join(script_lines) + '\r\n'
        script_path = root / UPDATER_SCRIPT_FILE
        script_path.write_text(script_content, encoding="utf-8")
        logger.info(f"[Update] Updater script ready: {script_path}")

        return {"success": True, "bat_path": str(script_path)}

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
