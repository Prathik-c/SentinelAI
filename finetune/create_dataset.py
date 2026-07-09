import sqlite3
import json
import os

DB_PATH = "../backend/data/sentinelai.db"
OUTPUT_PATH = "dataset/raw_incidents.json"

def export_health_data():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get all health logs
    cursor.execute("""
        SELECT timestamp, cpu, ram, disk, top_processes, idle_seconds
        FROM health_logs
        ORDER BY timestamp DESC
    """)
    logs = cursor.fetchall()

    # Get baseline stats
    cursor.execute("SELECT AVG(cpu), AVG(ram), COUNT(*) FROM health_logs")
    avg_cpu, avg_ram, total = cursor.fetchone()

    conn.close()

    return {
        "total_logs": total,
        "baseline": {
            "cpu_mean": round(avg_cpu, 1),
            "ram_mean": round(avg_ram, 1)
        },
        "logs": [
            {
                "timestamp": log[0],
                "cpu": log[1],
                "ram": log[2],
                "disk": log[3],
                "top_processes": json.loads(log[4]) if log[4] else [],
                "idle_seconds": log[5]
            }
            for log in logs
        ]
    }

def generate_raw_examples(data):
    examples = []
    logs = data["logs"]
    baseline = data["baseline"]

    for log in logs:
        cpu = log["cpu"]
        ram = log["ram"]
        processes = log["top_processes"]
        idle = log["idle_seconds"]
        timestamp = log["timestamp"]

        # Only generate examples for interesting moments
        # (anomalies or clear normal states)
        is_high_cpu = cpu > baseline["cpu_mean"] * 3
        is_high_ram = ram > baseline["ram_mean"] + 20
        is_idle = idle > 120
        top_proc_names = [p["name"] for p in processes[:3]]

        if is_high_cpu or is_high_ram:
            # Anomaly example
            examples.append({
                "type": "anomaly",
                "timestamp": timestamp,
                "cpu": cpu,
                "ram": ram,
                "idle_seconds": idle,
                "top_processes": top_proc_names,
                "is_high_cpu": is_high_cpu,
                "is_high_ram": is_high_ram
            })
        elif cpu < 10 and ram < 70 and idle > 5:
            # Normal state example
            examples.append({
                "type": "normal",
                "timestamp": timestamp,
                "cpu": cpu,
                "ram": ram,
                "idle_seconds": idle,
                "top_processes": top_proc_names,
                "is_high_cpu": False,
                "is_high_ram": False
            })

    return examples

if __name__ == "__main__":
    os.makedirs("dataset", exist_ok=True)
    data = export_health_data()
    examples = generate_raw_examples(data)

    with open(OUTPUT_PATH, "w") as f:
        json.dump({
            "baseline": data["baseline"],
            "total_logs": data["total_logs"],
            "examples": examples
        }, f, indent=2)

    print(f"Exported {len(examples)} raw examples from {data['total_logs']} logs")
    print(f"Saved to {OUTPUT_PATH}")