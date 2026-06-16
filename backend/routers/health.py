
from fastapi import APIRouter
from services.health_service import get_health_metrics
from fastapi import Depends
from sqlalchemy.orm import Session
from database import get_db
from models.tables import HealthLog


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