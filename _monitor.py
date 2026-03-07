"""Get detailed thread logs and errors."""
import requests
import json

API = "http://localhost:8000/api"

# Get thread logs from DB
try:
    r = requests.get(f"{API}/threads/")
    if r.status_code == 200:
        threads = r.json()
        print("=== THREAD LOGS ===")
        if isinstance(threads, list):
            for t in threads[-10:]:
                print(f"  T{t.get('thread_id','?')}: status={t.get('status','?')} step={t.get('current_step','?')}")
                if t.get('error_message'):
                    print(f"    ERROR: {t['error_message'][:200]}")
        else:
            print(json.dumps(threads, indent=2, default=str)[:1000])
except Exception as e:
    print(f"Thread logs error: {e}")

# Get errors
try:
    r = requests.get(f"{API}/errors/")
    if r.status_code == 200:
        errors = r.json()
        print("\n=== RECENT ERRORS ===")
        if isinstance(errors, list):
            for e in errors[-10:]:
                print(f"  [{e.get('created_at','')}] {e.get('message','')[:150]}")
        else:
            print(json.dumps(errors, indent=2, default=str)[:1000])
except Exception as e:
    print(f"Errors fetch error: {e}")

# Check birth status again
status = requests.get(f"{API}/birth/status").json()
print(f"\n=== STATUS: completed={status.get('completed')}, failed={status.get('failed')}, running={status.get('running')} ===")

# Check application logs
try:
    import os
    log_path = r"C:\Users\admin\Desktop\Leomail\app\user_data\logs\leomail.log"
    if os.path.exists(log_path):
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        # Get last 40 lines
        print("\n=== LAST 40 LOG LINES ===")
        for line in lines[-40:]:
            print(f"  {line.rstrip()}")
except Exception as e:
    print(f"Log read error: {e}")
