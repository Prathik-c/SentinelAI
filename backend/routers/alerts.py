"""
SentinelAI — Alerts Router

Fixed serialisation, added pagination, stats endpoint, and proper error handling.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from services import alert_service

router = APIRouter(prefix="/alerts", tags=["Alerts"])


class AlertActionRequest(BaseModel):
    action: str  # "approved" or "dismissed"


@router.get("")
def get_alerts(
    db:    Session = Depends(get_db),
    skip:  int = Query(default=0,   ge=0),
    limit: int = Query(default=100, ge=1, le=500),
):
    """
    Returns all detected behavioural anomalies, serialised as plain dicts.
    Supports pagination via skip/limit.
    """
    try:
        return alert_service.get_all_incidents(db, skip=skip, limit=limit)
    except Exception as exc:
        logger.error(f"GET /alerts error: {exc}")
        raise HTTPException(status_code=500, detail="Failed to retrieve alerts.")


@router.get("/stats")
def get_alert_stats(db: Session = Depends(get_db)):
    """Returns aggregate counts by status and severity for dashboard display."""
    try:
        return alert_service.get_incident_stats(db)
    except Exception as exc:
        logger.error(f"GET /alerts/stats error: {exc}")
        raise HTTPException(status_code=500, detail="Failed to retrieve alert stats.")


@router.post("/{alert_id}/action")
def update_alert_action(
    alert_id: int,
    request:  AlertActionRequest,
    db:       Session = Depends(get_db),
):
    """Confirms (approves) or dismisses a detected alert."""
    if request.action not in ("approved", "dismissed"):
        raise HTTPException(
            status_code=400,
            detail="Invalid action. Must be 'approved' or 'dismissed'.",
        )

    try:
        updated = alert_service.update_incident_status(db, alert_id, request.action)
    except Exception as exc:
        logger.error(f"POST /alerts/{alert_id}/action error: {exc}")
        raise HTTPException(status_code=500, detail="Failed to update alert status.")

    if not updated:
        raise HTTPException(
            status_code=404,
            detail=f"Alert with ID {alert_id} not found.",
        )

    return updated
