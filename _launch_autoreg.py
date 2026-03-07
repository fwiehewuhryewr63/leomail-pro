"""Launch Outlook autoreg: 2 accounts, 2 threads, Argentina (F)."""
import requests

API = "http://localhost:8000/api"

# 1. Find Argentina (F) pack ID
packs = requests.get(f"{API}/names/").json()
argentina_f = [p for p in packs if "Argentina" in p.get("name", "") and "(F)" in p.get("name", "")]
if not argentina_f:
    print("ERROR: Argentina (F) pack not found!")
    print("Available:", [p["name"] for p in packs if "Argentina" in p.get("name", "")])
    exit(1)

pack_id = argentina_f[0]["id"]
print(f"Found: Argentina (F) id={pack_id}")

# 2. Launch birth task
payload = {
    "provider": "outlook",
    "quantity": 2,
    "name_pack_ids": [pack_id],
    "threads": 2,
    "farm_name": "",
    "headless": True
}
print(f"Launching: {payload}")
r = requests.post(f"{API}/birth/start", json=payload)
print(f"Response ({r.status_code}): {r.json()}")
