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
from pathlib import Path

# ── Fix for PyInstaller windowed mode (no console) ──
if sys.stdin is None:
    sys.stdin = open(os.devnull, 'r')
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

# Log file for debugging
_log_file = None


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


def find_free_port(start=8000, end=8100) -> int:
    for port in range(start, end):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', port))
                return port
        except OSError:
            continue
    return start


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


def open_native_window(port: int):
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
        f"--app=http://127.0.0.1:{port}",
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
        "--disable-gpu-sandbox",
    ]

    log(f"[Leomail] Launching window...")
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log(f"[Leomail] Window opened (PID: {proc.pid})")

    # Wait for Chrome to close
    proc.wait()
    log("[Leomail] Window closed.")


def main():
    global _log_file
    root = get_app_root()

    # Open log file
    try:
        log_dir = root / "user_data" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        _log_file = open(str(log_dir / "launcher.log"), "w", encoding="utf-8")
    except Exception:
        pass

    # Ensure version.json is at app root for updater
    ensure_version_at_root()

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
        open_native_window(port)
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
