"""Launch single Yahoo birth via Leomail API"""
import urllib.request
import json
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE = "http://127.0.0.1:8000"

# 1. Get name packs
print("=== Name Packs ===")
r = urllib.request.urlopen(f"{BASE}/api/names/", timeout=5)
packs = json.loads(r.read())
ar_id = None
for p in packs:
    marker = " <<<" if "argentin" in p["name"].lower() else ""
    print(f"  id={p['id']:3d}  name={p['name']:30s}  count={p.get('count','?')}{marker}")
    if "argentin" in p["name"].lower():
        ar_id = p["id"]

if not ar_id:
    print("No Argentina pack, using first")
    ar_id = packs[0]["id"]

print(f"\n>>> Using pack ID: {ar_id}")

# 2. Launch birth
print("\n=== Launching Yahoo Birth ===")
payload = json.dumps({
    "provider": "yahoo",
    "quantity": 1,
    "device_type": "desktop",
    "name_pack_ids": [ar_id],
    "sms_provider": "simsms",
    "sms_countries": ["ar"],
    "threads": 1,
    "farm_name": "yahoo_test_ar",
    "headless": False
}).encode()

req = urllib.request.Request(
    f"{BASE}/api/birth/start",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST"
)
try:
    r = urllib.request.urlopen(req, timeout=10)
    result = json.loads(r.read())
    print(f"  Result: {json.dumps(result, indent=2)}")
except urllib.error.HTTPError as e:
    print(f"  HTTP Error {e.code}: {e.reason}")
    print(f"  Body: {e.read().decode()}")
except Exception as e:
    print(f"  Error: {e}")
