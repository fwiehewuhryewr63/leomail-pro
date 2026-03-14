"""
Leomail — Native Desktop Launcher
Runs backend server + opens Chromium in --app mode for native window.
"""
import os
import sys
import io
import json
import time
import threading
import socket
import subprocess
import shutil
import traceback
import re
import ctypes
from pathlib import Path

try:
    import psutil
except Exception:
    psutil = None

# ── Fix for PyInstaller windowed mode (no console) ──
if sys.stdin is None:
    sys.stdin = open(os.devnull, 'r')
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

# Log file for debugging
_log_file = None
_instance_mutex = None


def log(msg: str):
    """Safe logging to stdout + log file."""
    global _log_file
    try:
        line = f"{msg}\n"
        if sys.stdout and not sys.stdout.closed:
            sys.stdout.write(line)
            sys.stdout.flush()
        if _log_file and not _log_file.closed:
            _log_file.write(line)
            _log_file.flush()
    except Exception:
        pass


def show_error(title: str, message: str):
    """Show a visible Windows error dialog. Works in PyInstaller windowed mode."""
    log(f"[Leomail] ERROR DIALOG: {title} — {message}")
    try:
        import ctypes
        # MB_OK | MB_ICONERROR | MB_SETFOREGROUND
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x10 | 0x10000)
    except Exception:
        pass  # If MessageBox fails too, at least we logged it


def acquire_single_instance_guard():
    """
    Port probing alone is not strong enough during update/restart races.
    Use a Windows named mutex so a second launch cannot survive alongside the
    real boxed runtime.
    """
    global _instance_mutex
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    mutex_name = "Local\\Leomail.BoxedRuntime"
    handle = kernel32.CreateMutexW(None, False, mutex_name)
    if not handle:
        log("[Leomail] Warning: failed to create instance mutex; continuing with port guard only.")
        return

    _instance_mutex = handle
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        try:
            kernel32.CloseHandle(handle)
        except Exception:
            pass
        show_error(
            "Leomail - Already Running",
            "Another Leomail instance is already running or finishing an update.\n\n"
            "Wait a few seconds and try again.\n"
            "If an update is in progress, let it finish.\n\n"
            "Leomail will now exit."
        )
        sys.exit(1)


def get_app_root() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def read_version() -> str:
    """Read version from version.json (exe root → _MEIPASS → fallback)."""
    candidates = []
    if getattr(sys, 'frozen', False):
        candidates.append(Path(sys.executable).parent / "version.json")
        candidates.append(Path(sys._MEIPASS) / "version.json")
    candidates.append(Path(__file__).parent / "version.json")
    for vpath in candidates:
        if vpath.exists():
            try:
                data = json.loads(vpath.read_text(encoding="utf-8"))
                return data.get("version", "0.0.0")
            except Exception:
                continue
    return "0.0.0"


def parse_version_tuple(version: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", version or "")
    if not parts:
        return (0,)
    return tuple(int(part) for part in parts[:4])


def read_version_file(vpath: Path) -> str:
    try:
        data = json.loads(vpath.read_text(encoding="utf-8"))
        return data.get("version", "0.0.0")
    except Exception:
        return "0.0.0"


def ensure_version_at_root():
    """Copy version.json from _MEIPASS to exe root if missing (for updater.py)."""
    if not getattr(sys, 'frozen', False):
        return
    root_ver = Path(sys.executable).parent / "version.json"
    meipass_ver = Path(sys._MEIPASS) / "version.json"
    if not root_ver.exists() and meipass_ver.exists():
        try:
            shutil.copy2(str(meipass_ver), str(root_ver))
            log(f"[Leomail] Copied version.json to app root")
        except Exception as e:
            log(f"[Leomail] Warning: could not copy version.json: {e}")


def cleanup_stale_update_artifacts(root: Path, reason: str):
    for name in ["_updater.bat", "_update_launch.txt", "_update_started.txt"]:
        path = root / name
        try:
            if path.exists():
                path.unlink()
        except Exception as e:
            log(f"[Leomail] Warning: could not remove {name}: {e}")
    try:
        update_tmp = root / "_update_tmp"
        if update_tmp.exists():
            shutil.rmtree(str(update_tmp), ignore_errors=True)
    except Exception as e:
        log(f"[Leomail] Warning: could not remove _update_tmp: {e}")
    log(f"[Leomail] Cleared stale update artifacts: {reason}")


def read_staged_update_version(root: Path) -> str:
    update_tmp = root / "_update_tmp" / "extracted"
    if not update_tmp.exists():
        return "0.0.0"
    for vfile in update_tmp.rglob("version.json"):
        staged = read_version_file(vfile)
        if staged != "0.0.0":
            return staged
    return "0.0.0"


def resume_pending_update_if_needed(root: Path) -> bool:
    """
    If a staged update exists but never actually started applying, relaunch the
    local updater before booting the old runtime again.
    """
    if not getattr(sys, 'frozen', False):
        return False

    updater_bat = root / "_updater.bat"
    update_tmp = root / "_update_tmp"
    started_marker = root / "_update_started.txt"
    result_marker = root / "_update_result.txt"

    if result_marker.exists():
        return False
    if not updater_bat.exists() or not update_tmp.exists():
        if started_marker.exists() or (root / "_update_launch.txt").exists():
            cleanup_stale_update_artifacts(root, "markers without staged update")
        return False

    current_version = read_version()
    staged_version = read_staged_update_version(root)

    if staged_version == "0.0.0":
        cleanup_stale_update_artifacts(root, "staged update missing version metadata")
        return False

    if parse_version_tuple(staged_version) <= parse_version_tuple(current_version):
        cleanup_stale_update_artifacts(
            root,
            f"staged version {staged_version} is not newer than current version {current_version}",
        )
        return False

    if started_marker.exists():
        log(f"[Leomail] Staged update {staged_version} already acknowledged; letting updater continue.")
        return False

    log("[Leomail] Pending staged update detected before startup. Relaunching updater...")
    try:
        subprocess.Popen(
            ["cmd.exe", "/d", "/c", str(updater_bat)],
            cwd=str(root),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        log("[Leomail] Updater relaunch dispatched. Exiting old runtime so apply can continue.")
        return True
    except Exception as e:
        log(f"[Leomail] Failed to relaunch staged updater: {e}")
        return False


def _can_bind_local_port(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', port))
            return True
    except OSError:
        return False


def find_free_port(start=8000, end=8100) -> int:
    """
    In boxed EXE mode Leomail should behave like a single desktop app, not
    silently spin up shadow instances on 8001/8002. Dev mode still keeps the
    old scan behavior for convenience.
    """
    if getattr(sys, 'frozen', False):
        fixed_port = 8000
        if _can_bind_local_port(fixed_port):
            return fixed_port
        show_error(
            "Leomail — Already Running",
            "Another Leomail instance is still running or shutting down.\n\n"
            "Wait a few seconds and try again.\n"
            "If an update is in progress, let it finish.\n\n"
            "Leomail will now exit."
        )
        sys.exit(1)

    for port in range(start, end):
        if _can_bind_local_port(port):
            return port

    show_error(
        "Leomail — Port Conflict",
        f"Could not find a free port in range {start}-{end}.\n\n"
        "Another Leomail instance may already be running.\n"
        "Close it and try again.\n\n"
        "Leomail will now exit."
    )
    sys.exit(1)


def start_backend(port: int):
    import uvicorn
    root = get_app_root()
    if getattr(sys, 'frozen', False):
        meipass = Path(sys._MEIPASS)
        os.chdir(str(meipass))
        if str(meipass) not in sys.path:
            sys.path.insert(0, str(meipass))
        log(f"[Leomail] _MEIPASS: {meipass}")
    else:
        os.chdir(str(root))
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
    uvicorn.run("backend.main:app", host="127.0.0.1", port=port, log_level="info")


def wait_for_backend(port: int, timeout: int = 30) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                s.connect(('127.0.0.1', port))
                return True
        except (ConnectionRefusedError, socket.timeout, OSError):
            time.sleep(0.5)
    return False


def find_chromium() -> str:
    """Find Playwright's installed Chromium or system Chrome."""
    # 1. Playwright's Chromium
    pw_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
    if pw_dir.exists():
        for d in sorted(pw_dir.iterdir(), reverse=True):
            if d.name.startswith("chromium"):
                chrome = d / "chrome-win64" / "chrome.exe"
                if chrome.exists():
                    return str(chrome)
                chrome = d / "chrome-win" / "chrome.exe"
                if chrome.exists():
                    return str(chrome)

    # 2. System Chrome
    for path in [
        os.environ.get("PROGRAMFILES", "") + r"\Google\Chrome\Application\chrome.exe",
        os.environ.get("PROGRAMFILES(X86)", "") + r"\Google\Chrome\Application\chrome.exe",
        os.environ.get("LOCALAPPDATA", "") + r"\Google\Chrome\Application\chrome.exe",
    ]:
        if os.path.exists(path):
            return path

    return ""


def open_native_window(port: int, version: str):
    """Open Chromium/Chrome in --app mode (native window, no tabs)."""
    chrome_path = find_chromium()
    if not chrome_path:
        log("[Leomail] FATAL: No Chromium/Chrome found!")
        log("[Leomail] User needs to install Google Chrome or reinstall Leomail.")
        show_error(
            "Leomail — Browser Not Found",
            "Google Chrome is required but was not found on this system.\n\n"
            "To fix this, please try one of the following:\n"
            "• Install Google Chrome (https://google.com/chrome)\n"
            "• Reinstall or update Leomail\n"
            "• Contact support\n\n"
            "Leomail will now exit."
        )
        sys.exit(1)

    log(f"[Leomail] Using: {chrome_path}")

    # Create a dedicated user-data-dir so --app mode works clean
    root = get_app_root()
    user_data = root / "user_data" / "chromium_profile"
    user_data.mkdir(parents=True, exist_ok=True)

    cmd = [
        chrome_path,
        f"--app=http://127.0.0.1:{port}/?v={version}",
        f"--user-data-dir={user_data}",
        "--window-size=1400,900",
        "--disable-extensions",
        "--disable-default-apps",
        "--no-first-run",
        "--disable-infobars",
        "--disable-http-cache",
        "--disable-background-networking",
        # ── Stability: prevent "Aw, Snap!" Error code 15 (GPU crash) ──
        "--disable-gpu",
        "--disable-software-rasterizer",
        "--in-process-gpu",
    ]

    log(f"[Leomail] Launching window...")
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log(f"[Leomail] Window opened (PID: {proc.pid})")

    # On Windows, the initial chrome.exe process can exit immediately after
    # spawning the real app-window process. If we just `wait()` on the first
    # PID, Leomail.exe dies, the backend thread dies with it, and the orphaned
    # app window is left showing 127.0.0.1 refused. Track the real app window.
    app_url = f"http://127.0.0.1:{port}/?v={version}".lower()
    profile_marker = str(user_data).lower()

    if psutil:
        app_pid = None
        appear_deadline = time.time() + 15
        while time.time() < appear_deadline:
            app_pids = []
            for p in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    name = (p.info.get("name") or "").lower()
                    if "chrome" not in name:
                        continue
                    cmdline = " ".join(p.info.get("cmdline") or []).lower()
                    if "--app=" in cmdline and app_url in cmdline and profile_marker in cmdline:
                        app_pids.append(p.info["pid"])
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
            if app_pids:
                app_pid = app_pids[0]
                log(f"[Leomail] App window attached (PID: {app_pid})")
                break
            time.sleep(0.5)

        if app_pid:
            while True:
                try:
                    if not psutil.pid_exists(app_pid):
                        break
                except Exception:
                    break
                time.sleep(1)
        else:
            # Fallback if we fail to detect the handoff PID.
            proc.wait()
    else:
        proc.wait()
    log("[Leomail] Window closed.")


def main():
    try:
        _main_inner()
    except SystemExit:
        raise  # Allow clean sys.exit() calls
    except KeyboardInterrupt:
        pass
    except Exception as e:
        # Log to file if possible
        log(f"[Leomail] FATAL UNHANDLED ERROR: {e}")
        log(traceback.format_exc())
        show_error(
            "Leomail — Fatal Error",
            f"Leomail encountered an unexpected error and cannot start.\n\n"
            f"Error: {e}\n\n"
            f"Check user_data/logs/launcher.log for details.\n\n"
            f"Leomail will now exit."
        )
        sys.exit(1)


def _main_inner():
    global _log_file
    root = get_app_root()

    # Open log file (append mode to preserve previous crash evidence)
    try:
        log_dir = root / "user_data" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        _log_file = open(str(log_dir / "launcher.log"), "a", encoding="utf-8")
        _log_file.write(f"\n{'=' * 60}\n")
    except Exception:
        pass

    acquire_single_instance_guard()

    # Ensure version.json is at app root for updater
    ensure_version_at_root()

    if resume_pending_update_if_needed(root):
        sys.exit(0)

    version = read_version()
    port = find_free_port()

    log(f"[Leomail] v{version}")
    log(f"[Leomail] Root: {root}")
    log(f"[Leomail] Port: {port}")

    # Start backend in background thread
    backend_thread = threading.Thread(target=start_backend, args=(port,), daemon=True)
    backend_thread.start()

    # Wait for backend
    log("[Leomail] Starting backend...")
    if not wait_for_backend(port, timeout=30):
        log("[Leomail] ERROR: Backend failed to start!")
        show_error(
            "Leomail — Startup Failed",
            "The backend server failed to start within 30 seconds.\n\n"
            "Check user_data/logs/launcher.log for details.\n\n"
            "Leomail will now exit."
        )
        sys.exit(1)

    log(f"[Leomail] Backend ready on :{port}")

    # Open native app window
    try:
        open_native_window(port, version)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log(f"[Leomail] FATAL: Window failed to open: {e}")
        log(traceback.format_exc())
        show_error(
            "Leomail — Window Error",
            f"Failed to open the application window.\n\n"
            f"Error: {e}\n\n"
            f"Check user_data/logs/launcher.log for details.\n\n"
            f"Leomail will now exit."
        )
        sys.exit(1)

    # Normal close: Chrome window closed, backend is daemon thread (auto-dies).
    # sys.exit raises SystemExit → allows Python cleanup (lifespan, logs, DB).
    sys.exit(0)


if __name__ == "__main__":
    main()
