import sqlite3

db_path = "user_data/leomail.db"
conn = sqlite3.connect(db_path)
c = conn.cursor()

# Check current state
c.execute("SELECT COUNT(*) FROM proxies WHERE use_yahoo=1")
yahoo_enabled = c.fetchone()[0]
c.execute("SELECT COUNT(*) FROM proxies WHERE status='active'")
active = c.fetchone()[0]
print(f"Active proxies: {active}, Yahoo-enabled: {yahoo_enabled}")

if yahoo_enabled == 0:
    # Enable use_yahoo on first 5 active socks5/http proxies
    c.execute("""UPDATE proxies SET use_yahoo=1 
                 WHERE status='active' AND proxy_type IN ('socks5','http') 
                 AND id IN (SELECT id FROM proxies WHERE status='active' ORDER BY id LIMIT 5)""")
    updated = c.rowcount
    conn.commit()
    print(f"Enabled use_yahoo on {updated} proxies")
else:
    print("Yahoo already enabled on some proxies")

# Verify
c.execute("SELECT id, host, port, proxy_type, use_yahoo FROM proxies WHERE use_yahoo=1")
for r in c.fetchall():
    print(f"  id={r[0]} {r[1]}:{r[2]} type={r[3]} use_yahoo={r[4]}")

conn.close()
