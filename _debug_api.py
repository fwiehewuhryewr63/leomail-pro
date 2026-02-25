import urllib.request
import json

BASE = "http://127.0.0.1:8000"

# Try openapi docs to find routes
try:
    r = urllib.request.urlopen(f"{BASE}/openapi.json", timeout=5)
    spec = json.loads(r.read())
    paths = list(spec.get("paths", {}).keys())
    # Filter for birth and names
    for p in paths:
        if "name" in p.lower() or "birth" in p.lower() or "prox" in p.lower():
            print(p)
except Exception as e:
    print(f"openapi error: {e}")

# Try direct
for url in [f"{BASE}/api/names", f"{BASE}/api/names/", f"{BASE}/api/proxies", f"{BASE}/api/birth/status"]:
    try:
        r = urllib.request.urlopen(url, timeout=3)
        print(f"OK {url} -> {r.status}")
    except Exception as e:
        print(f"FAIL {url} -> {e}")
