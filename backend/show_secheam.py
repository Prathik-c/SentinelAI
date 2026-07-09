import sqlite3

conn = sqlite3.connect("data/sentinelai.db")
cursor = conn.cursor()

cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()

for name, sql in tables:
    print(f"--- {name} ---")
    print(sql)
    print()

conn.close()