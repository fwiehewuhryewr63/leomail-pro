"""Copy proxies from VPS (Desktop user_data) DB to local DB and enable Yahoo"""
import sqlite3

VPS_DB = "C:/Users/admin/Desktop/user_data/leomail.db"
LOCAL_DB = "user_data/leomail.db"

# Read proxies from VPS
vps = sqlite3.connect(VPS_DB)
vc = vps.cursor()
vc.execute("SELECT host, port, username, password, protocol, proxy_type, status, geo FROM proxies WHERE status='active' LIMIT 5")
proxies = vc.fetchall()
print(f"Found {len(proxies)} active proxies in VPS DB")
vps.close()

if not proxies:
    print("No active proxies in VPS DB!")
    exit(1)

# Insert into local DB (with use_yahoo=1)
local = sqlite3.connect(LOCAL_DB)
lc = local.cursor()

# Check columns
lc.execute("PRAGMA table_info(proxies)")
cols = [r[1] for r in lc.fetchall()]
print(f"Local proxy columns: {cols}")

inserted = 0
for p in proxies:
    host, port, user, pwd, protocol, ptype, status, geo = p
    # Check if already exists
    lc.execute("SELECT id FROM proxies WHERE host=? AND port=?", (host, port))
    if lc.fetchone():
        print(f"  SKIP {host}:{port} (already exists)")
        continue
    lc.execute("""INSERT INTO proxies (host, port, username, password, protocol, proxy_type, status, geo, 
                  use_yahoo, use_aol, use_outlook, use_hotmail, use_gmail, fail_count)
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1, 1, 1, 0, 0)""",
               (host, port, user, pwd, protocol, ptype, status, geo))
    inserted += 1
    print(f"  ADD {host}:{port} ({ptype}, {geo}) use_yahoo=1")

local.commit()
print(f"\nInserted {inserted} proxies with Yahoo enabled")

# Verify
lc.execute("SELECT COUNT(*) FROM proxies WHERE status='active'")
print(f"Total active proxies in local DB: {lc.fetchone()[0]}")
lc.execute("SELECT COUNT(*) FROM proxies WHERE use_yahoo=1")
print(f"Yahoo-enabled proxies: {lc.fetchone()[0]}")

local.close()
