import json
import psutil

def get_health_metrics():
    return {
        "cpu": psutil.cpu_percent(interval=0.5),
        "ram": psutil.virtual_memory().percent,
        "disk": psutil.disk_usage('C:').percent,
    }

def get_top_processes(limit=5):
    processes = []
    for proc in psutil.process_iter(['name', 'cpu_percent', 'memory_percent']):
        try:
            info = proc.info
            if info['name'] in ("System Idle Process", "System", ""):
                continue
            if info['cpu_percent'] is not None:
                processes.append({
                    "name": info['name'],
                    "cpu": round(info['cpu_percent'], 1),
                    "ram": round(info['memory_percent'], 1)
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    processes.sort(key=lambda p: p['cpu'], reverse=True)
    return processes[:limit]

def log_health_snapshot(db):
    from models.tables import HealthLog
    from services.activity_service import get_idle_seconds

    metrics = get_health_metrics()
    processes = get_top_processes()
    idle = get_idle_seconds()

    log_entry = HealthLog(
        cpu=metrics["cpu"],
        ram=metrics["ram"],
        disk=metrics["disk"],
        top_processes=json.dumps(processes),
        idle_seconds=round(idle, 1)
    )
    db.add(log_entry)
    db.commit()
    return log_entry