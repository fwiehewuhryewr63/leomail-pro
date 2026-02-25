"""Load proxies from Desktop user_data/leomail.db"""
import sqlite3

DB = r"C:\Users\admin\Desktop\user_data\leomail.db"
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("PRAGMA table_info(proxies)")
cols = cur.fetchall()
col_names = [c[1] for c in cols]
print("Columns:", col_names)
cur.execute("SELECT * FROM proxies")
rows = cur.fetchall()
print(f"\n{len(rows)} proxies:")
for row in rows:
    d = dict(zip(col_names, row))
    sid = d.get("id", "?")
    s = d.get("status", "?")
    dt = d.get("device_type", "?")
    h = d.get("host", "?")
    p = d.get("port", "?")
    u = d.get("username", "")
    pw = d.get("password", "")
    pr = d.get("protocol", "?")
    gu = d.get("used_gmail", 0)
    auth = f"{u}:{pw}" if u else "no-auth"
    print(f"  id={sid} [{s}] [{dt}] {pr}://{auth}@{h}:{p} gmail={gu}")
conn.close()
