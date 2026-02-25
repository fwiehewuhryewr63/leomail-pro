"""Enable Yahoo on all proxies in local DB and re-launch birth"""
import sqlite3
import urllib.request
import json

# Enable Yahoo on all proxies
db = sqlite3.connect("user_data/leomail.db")
c = db.cursor()
c.execute("UPDATE proxies SET use_yahoo=1, use_aol=1, use_outlook=1, use_hotmail=1")
print(f"Enabled all providers on {c.rowcount} proxies")
db.commit()

c.execute("SELECT id, host, port, proxy_type, status, use_yahoo FROM proxies")
for r in c.fetchall():
    print(f"  id={r[0]} {r[1]}:{r[2]} type={r[3]} status={r[4]} yahoo={r[5]}")
db.close()

# Re-launch Yahoo birth
print("\n=== Re-launching Yahoo Birth ===")
payload = json.dumps({
    "provider": "yahoo",
    "quantity": 1,
    "device_type": "desktop",
    "name_pack_ids": [9],
    "sms_provider": "simsms",
    "sms_countries": ["ar"],
    "threads": 1,
    "farm_name": "yahoo_test_ar",
    "headless": False
}).encode()

req = urllib.request.Request(
    "http://127.0.0.1:8000/api/birth/start",
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
    body = e.read().decode()
    print(f"  Body: {body}")
except Exception as e:
    print(f"  Error: {e}")
