import sqlite3
conn = sqlite3.connect("C:/Users/admin/Desktop/user_data/leomail.db")
c = conn.cursor()
# First check table structure
c.execute("PRAGMA table_info(proxies)")
cols = [r[1] for r in c.fetchall()]
print("Columns:", cols)
# Get first 3 alive proxies with all data
c.execute("SELECT * FROM proxies LIMIT 3")
rows = c.fetchall()
for r in rows:
    print(dict(zip(cols, r)))
conn.close()
