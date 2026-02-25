import requests
import json

API = "http://185.229.251.188:8000/api"

# Get all name packs
packs = requests.get(f"{API}/names/").json()
print(f"Total packs: {len(packs)}")

# Find old small packs (< 500 names) to delete
old_ids = []
for p in packs:
    if p["total_count"] < 500:
        old_ids.append(p["id"])
        print(f"  DELETE: id={p['id']} count={p['total_count']}")

if old_ids:
    print(f"\nDeleting {len(old_ids)} old small packs...")
    r = requests.post(f"{API}/names/batch-delete", json={"ids": old_ids})
    print(f"Result: {r.status_code} {r.text}")
else:
    print("No old packs to delete")

# Verify
packs2 = requests.get(f"{API}/names/").json()
print(f"\nRemaining packs: {len(packs2)}")
total_names = sum(p["total_count"] for p in packs2)
print(f"Total names: {total_names}")
