import sqlite3

conn = sqlite3.connect("data/sentinelai.db")
cursor = conn.cursor()

# Count rows
cursor.execute("SELECT COUNT(*) FROM health_logs")
print("Total rows:", cursor.fetchone()[0])

# Show the ID range
cursor.execute("SELECT MIN(id), MAX(id) FROM health_logs")
print("Min ID, Max ID:", cursor.fetchone())

# Show the latest 5 rows
cursor.execute("SELECT * FROM health_logs ORDER BY id DESC LIMIT 5")

print("\nLatest 5 rows:")
for row in cursor.fetchall():
    print(row)

conn.close()