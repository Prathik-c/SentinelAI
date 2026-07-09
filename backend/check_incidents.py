import sqlite3

conn = sqlite3.connect("data/sentinelai.db")
c = conn.cursor()

c.execute("SELECT COUNT(*) FROM incidents")
total = c.fetchone()[0]
print("total incident rows:", total)

c.execute("SELECT COUNT(*) FROM incidents WHERE report IS NOT NULL AND report != ''")
with_report = c.fetchone()[0]
print("rows with report:", with_report)

# show a sample row so we can see what's actually stored
c.execute("SELECT id, timestamp, type, severity, description, report FROM incidents LIMIT 3")
rows = c.fetchall()
print("\nsample rows:")
for r in rows:
    print(r)

conn.close()