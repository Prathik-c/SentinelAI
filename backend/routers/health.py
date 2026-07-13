"""
SentinelAI — Health Router

Thin route layer — all business logic is delegated to services.
Every endpoint has proper exception handling and returns meaningful error messages.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from sqlalchemy.orm import Session

from core.exceptions import BaselineNotReadyError
from database import get_db
from services.health_service import get_health_metrics
from services.incident_engine import run_anomaly_check

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/current")
def current_health():
    """Returns live CPU, RAM, and Disk utilisation."""
    try:
        return get_health_metrics()
    except Exception as exc:
        logger.error(f"GET /health/current error: {exc}")
        raise HTTPException(status_code=500, detail="Failed to read system metrics.")


@router.get("/history")
def health_history(
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=500),
    skip:  int = Query(default=0,  ge=0),
):
    """Returns paginated health log history, most recent first."""
    from models.tables import HealthLog
    import json

    try:
        logs = (
            db.query(HealthLog)
            .order_by(HealthLog.timestamp.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return [
            {
                "id":            log.id,
                "timestamp":     str(log.timestamp),
                "cpu":           log.cpu,
                "ram":           log.ram,
                "disk":          log.disk,
                "top_processes": _safe_json(log.top_processes),
                "idle_seconds":  log.idle_seconds,
            }
            for log in logs
        ]
    except Exception as exc:
        logger.error(f"GET /health/history error: {exc}")
        raise HTTPException(status_code=500, detail="Failed to retrieve health history.")


@router.get("/baseline")
def get_baseline(db: Session = Depends(get_db)):
    """
    Returns the cached behavioural baseline statistics.
    Returns a 'learning' status if not enough data has been collected yet.
    """
    try:
        from services.baseline_engine import get_cached_baseline
        stats = get_cached_baseline(db)
        return {
            "total_samples": stats.sample_count,
            "cpu": {
                "mean": stats.cpu_mean,
                "std":  stats.cpu_std,
                "max":  stats.cpu_max,
                "min":  stats.cpu_min,
                "p95":  stats.cpu_p95,
            },
            "ram": {
                "mean": stats.ram_mean,
                "std":  stats.ram_std,
                "max":  stats.ram_max,
                "min":  stats.ram_min,
                "p95":  stats.ram_p95,
            },
            "disk": {
                "mean": stats.disk_mean,
            },
            "thresholds": {
                "cpu": stats.cpu_threshold,
                "ram": stats.ram_threshold,
            },
            "common_processes": [
                {
                    "name":        ps.name,
                    "appearances": ps.count,
                    "avg_cpu":     ps.avg_cpu,
                    "avg_ram":     ps.avg_ram,
                }
                for ps in sorted(
                    stats.known_processes.values(),
                    key=lambda x: x.count,
                    reverse=True,
                )[:10]
            ],
        }
    except BaselineNotReadyError as exc:
        return {"error": exc.message, "status": "learning"}
    except Exception as exc:
        logger.error(f"GET /health/baseline error: {exc}")
        raise HTTPException(status_code=500, detail="Failed to compute baseline.")


@router.get("/anomaly/check")
def check_anomaly(
    db: Session = Depends(get_db),
    cpu_mult:   float = Query(default=3.0, ge=1.0, le=10.0),
    ram_margin: float = Query(default=20.0, ge=0.0, le=50.0),
):
    """
    Runs the full anomaly detection pipeline and returns structured results.
    
    Key behaviour change from v1:
    - Python detects anomalies instantly (< 100ms).
    - LLM explanations are generated asynchronously in the background.
    - This endpoint NEVER blocks on an LLM call.
    - Incidents are saved to DB immediately; `report` field fills in ~10s.
    """
    try:
        return run_anomaly_check(db)
    except Exception as exc:
        logger.error(f"GET /health/anomaly/check error: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Anomaly check failed: {str(exc)}"
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_json(value):
    """Safely parses a JSON string, returning None on failure."""
    if not value:
        return None
    import json
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None