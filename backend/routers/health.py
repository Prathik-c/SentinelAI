
from fastapi import APIRouter
from services.health_service import get_health_metrics
from fastapi import Depends
from sqlalchemy.orm import Session
from database import get_db
from models.tables import HealthLog
from services.llm_service import explain_anomalies



router = APIRouter(prefix="/health", tags=["Health"])

@router.get("/current")
def current_health():
    return get_health_metrics()

@router.get("/history")
def health_history(db: Session = Depends(get_db), limit: int = 50):
    logs = db.query(HealthLog).order_by(HealthLog.timestamp.desc()).limit(limit).all()
    return [
        {
            "id": log.id,
            "timestamp": str(log.timestamp),
            "cpu": log.cpu,
            "ram": log.ram,
            "disk": log.disk,
            "top_processes": log.top_processes,
            "idle_seconds": log.idle_seconds
        }
        for log in logs
    ]

@router.get("/baseline")
def get_baseline(db: Session = Depends(get_db)):
    import json
    from sqlalchemy import func

    logs = db.query(HealthLog).all()

    if not logs:
        return {"error": "Not enough data"}

    cpu_values = [l.cpu for l in logs]
    ram_values = [l.ram for l in logs]
    disk_values = [l.disk for l in logs]

    # Count process frequency across all logs
    process_counts = {}
    for log in logs:
        if log.top_processes:
            processes = json.loads(log.top_processes)
            for p in processes:
                name = p["name"]
                process_counts[name] = process_counts.get(name, 0) + 1

    # Sort by frequency — most common processes = "normal" processes
    common_processes = sorted(
        process_counts.items(), key=lambda x: x[1], reverse=True
    )[:10]

    return {
        "total_samples": len(logs),
        "cpu": {
            "mean": round(sum(cpu_values) / len(cpu_values), 1),
            "max": round(max(cpu_values), 1),
            "min": round(min(cpu_values), 1),
        },
        "ram": {
            "mean": round(sum(ram_values) / len(ram_values), 1),
            "max": round(max(ram_values), 1),
            "min": round(min(ram_values), 1),
        },
        "disk": {
            "mean": round(sum(disk_values) / len(disk_values), 1),
        },
        "common_processes": [
            {"name": name, "appearances": count}
            for name, count in common_processes
        ]
    }
@router.get("/anomaly/check")
def check_anomaly(db: Session = Depends(get_db)):
    import json

    
    all_logs = db.query(HealthLog).all()

    if len(all_logs) < 50:
        return {"status": "learning", 
                "message": "Still learning your patterns — check back after more data is collected"}

    cpu_values = [l.cpu for l in all_logs]
    ram_values = [l.ram for l in all_logs]

    cpu_mean = sum(cpu_values) / len(cpu_values)
    ram_mean = sum(ram_values) / len(ram_values)

    # Dynamic thresholds — 3x mean for CPU, mean + 20% for RAM
    cpu_threshold = min(cpu_mean * 3, 40.0)
    ram_threshold = min(ram_mean + 20.0, 90.0)

    # Known processes from THIS user's history
    process_counts = {}
    for log in all_logs:
        if log.top_processes:
            for p in json.loads(log.top_processes):
                name = p["name"]
                process_counts[name] = process_counts.get(name, 0) + 1

    # Process is "known" if it appeared in at least 5% of logs
    min_appearances = len(all_logs) * 0.05
    known_processes = {
        name for name, count in process_counts.items()
        if count >= min_appearances
    }

    # Now check recent logs against THIS user's baseline
    recent = db.query(HealthLog).order_by(
        HealthLog.timestamp.desc()
    ).limit(5).all()

    anomalies = []
    for log in recent:
        if log.cpu > cpu_threshold:
            anomalies.append({
                "timestamp": str(log.timestamp),
                "type": "high_cpu",
                "severity": "critical" if log.cpu > 80 else "medium",
                "detail": f"CPU at {log.cpu}% — your normal is {round(cpu_mean, 1)}%"
            })

        if log.ram > ram_threshold:
            anomalies.append({
                "timestamp": str(log.timestamp),
                "type": "high_ram",
                "severity": "medium",
                "detail": f"RAM at {log.ram}% — your normal is {round(ram_mean, 1)}%"
            })

        if log.top_processes:
            for p in json.loads(log.top_processes):
                if (p["name"] not in known_processes
                        and p["cpu"] > 5.0
                        and p["name"] != ""):
                    anomalies.append({
                        "timestamp": str(log.timestamp),
                        "type": "unknown_process",
                        "severity": "high",
                        "detail": f"Unfamiliar process '{p['name']}' using {p['cpu']}% CPU — not seen in your normal usage"
                    })

        baseline_context = {
        "cpu_mean": round(cpu_mean, 1),
        "ram_mean": round(ram_mean, 1),
        "cpu_threshold": round(cpu_threshold, 1),
        "ram_threshold": round(ram_threshold, 1),
        "baseline_samples": len(all_logs)
    }

    explanation = explain_anomalies(anomalies, baseline_context)

    return {
        "status": "anomalies_found" if anomalies else "normal",
        "baseline_samples": len(all_logs),
        "your_normal": baseline_context,
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
        "explanation": explanation      # LLM-generated plain English explanation
    }