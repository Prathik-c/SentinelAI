# backend/services/health_service.py
import psutil

def get_health_metrics():
    return {
        "cpu": psutil.cpu_percent(interval=0.5),
        "ram": psutil.virtual_memory().percent,
        "disk": psutil.disk_usage('C:').percent,
    }