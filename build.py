"""
Leomail Build Script
Creates a distributable Windows app that bundles:
- Python backend (FastAPI + all modules)
- React frontend (compiled dist/)

Usage: python build.py
Output: dist/Leomail/Leomail.exe
"""
import subprocess
import sys
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
FRONTEND = ROOT / "frontend"
BACKEND = ROOT / "backend"
DIST = ROOT / "dist"

def build_frontend():
    print("[1/3] Building React frontend...")
    result = subprocess.run(
        ["cmd", "/c", "npm", "run", "build"],
        cwd=str(FRONTEND),
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"Frontend build failed:\n{result.stderr}")
        sys.exit(1)
    print("  OK: Frontend built to frontend/dist/")

def build_exe():
    print("[2/3] Packaging with PyInstaller...")
    
    # Create entry point script
    entry_script = ROOT / "leomail_entry.py"
    entry_script.write_text("""
import os
import sys
import webbrowser
import threading
import uvicorn

# Set working directory to where the EXE is
if getattr(sys, 'frozen', False):
    os.chdir(os.path.dirname(sys.executable))

# Ensure user_data exists
os.makedirs("user_data", exist_ok=True)

def open_browser():
    import time
    time.sleep(2)
    webbrowser.open("http://localhost:8000")

# Open browser after server starts
threading.Thread(target=open_browser, daemon=True).start()

# Start the server
print("=" * 50)
print("  LEOMAIL v0.1 - Email Lifecycle Engine")
print("  Server: http://localhost:8000")
print("  Press Ctrl+C to stop")
print("=" * 50)

from backend.main import app
uvicorn.run(app, host="0.0.0.0", port=8000)
""", encoding="utf-8")

    # Collect data files
    frontend_dist = FRONTEND / "dist"
    
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=Leomail",
        "--onedir",
        "--console",
        f"--add-data={frontend_dist};frontend/dist",
        "--hidden-import=uvicorn",
        "--hidden-import=uvicorn.logging",
        "--hidden-import=uvicorn.loops",
        "--hidden-import=uvicorn.loops.auto",
        "--hidden-import=uvicorn.protocols",
        "--hidden-import=uvicorn.protocols.http",
        "--hidden-import=uvicorn.protocols.http.auto",
        "--hidden-import=uvicorn.protocols.websockets",
        "--hidden-import=uvicorn.protocols.websockets.auto",
        "--hidden-import=uvicorn.lifespan",
        "--hidden-import=uvicorn.lifespan.on",
        "--hidden-import=uvicorn.lifespan.off",
        "--hidden-import=fastapi",
        "--hidden-import=sqlalchemy",
        "--hidden-import=sqlalchemy.dialects.sqlite",
        "--hidden-import=pydantic",
        "--hidden-import=loguru",
        "--hidden-import=backend",
        "--hidden-import=backend.main",
        "--hidden-import=backend.database",
        "--hidden-import=backend.models",
        "--hidden-import=backend.config",
        "--hidden-import=backend.schemas",
        "--hidden-import=backend.utils",
        "--hidden-import=backend.routers",
        "--hidden-import=backend.routers.proxies",
        "--hidden-import=backend.routers.services",
        "--hidden-import=backend.routers.birth",
        "--hidden-import=backend.routers.dashboard",
        "--hidden-import=backend.routers.settings",
        "--hidden-import=backend.services",
        "--hidden-import=backend.services.sms_provider",
        "--hidden-import=backend.services.captcha_provider",
        "--hidden-import=backend.modules",
        "--hidden-import=backend.modules.birth",
        "--hidden-import=backend.modules.birth.outlook",
        "--hidden-import=backend.modules.birth.gmail",
        "--hidden-import=backend.modules.browser_manager",
        "--hidden-import=backend.routers.ai",
        "--hidden-import=backend.services.ai_provider",
        "--noconfirm",
        str(entry_script)
    ]
    
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        print("PyInstaller build failed!")
        sys.exit(1)
    
    # Copy backend source into dist (PyInstaller doesn't handle relative imports well)
    dest_backend = DIST / "Leomail" / "backend"
    if dest_backend.exists():
        shutil.rmtree(dest_backend)
    shutil.copytree(BACKEND, dest_backend, ignore=shutil.ignore_patterns("__pycache__"))
    
    print("  OK: EXE packaged to dist/Leomail/")

def finalize():
    print("[3/3] Finalizing...")
    
    # Create user_data template
    user_data = DIST / "Leomail" / "user_data"
    user_data.mkdir(exist_ok=True)
    
    print("  OK: Ready!")
    print()
    print("=" * 50)
    print("  BUILD COMPLETE")
    print(f"  Output: {DIST / 'Leomail'}")
    print("  Copy the 'Leomail' folder to your server")
    print("  Run: Leomail.exe")
    print("=" * 50)

if __name__ == "__main__":
    build_frontend()
    build_exe()
    finalize()
