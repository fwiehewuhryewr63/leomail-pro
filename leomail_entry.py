
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
