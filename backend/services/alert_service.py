"""
SentinelAI — Alert Service

Fixed serialisation (SQLAlchemy objects → plain dicts), added path guards,
pagination, and stats endpoint support.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy.orm import Session

from config import SNAPSHOTS_PATH


# ── Incident Serialisation ────────────────────────────────────────────────────

def _serialise_incident(incident) -> Dict[str, Any]:
    """
    Converts a SQLAlchemy Incident ORM object to a plain dict safe for JSON.
    Handles missing/null fields gracefully.
    """
    import json as _json

    reasons = []
    if incident.reasons:
        try:
            reasons = _json.loads(incident.reasons)
        except (_json.JSONDecodeError, TypeError):
            reasons = []

    return {
        "id":           incident.id,
        "timestamp":    str(incident.timestamp),
        "type":         incident.type or "anomaly",
        "severity":     incident.severity or "medium",
        "status":       incident.status or "pending",
        "description":  incident.description,
        "process_name": incident.process_name,
        "risk_score":   incident.risk_score,
        "reasons":      reasons,
        "report":       incident.report,
        "approved_at":  str(incident.approved_at) if incident.approved_at else None,
    }


# ── Queries ───────────────────────────────────────────────────────────────────

def get_all_incidents(
    db: Session,
    skip: int = 0,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Returns all incidents ordered by timestamp desc, serialised as dicts."""
    from models.tables import Incident

    incidents = (
        db.query(Incident)
        .order_by(Incident.timestamp.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_serialise_incident(i) for i in incidents]


def get_incident_stats(db: Session) -> Dict[str, Any]:
    """Returns aggregate counts by status and severity for dashboard display."""
    from models.tables import Incident
    from sqlalchemy import func

    results = (
        db.query(
            Incident.status,
            Incident.severity,
            func.count(Incident.id).label("count"),
        )
        .group_by(Incident.status, Incident.severity)
        .all()
    )

    stats: Dict[str, Any] = {
        "by_status":   {"pending": 0, "approved": 0, "dismissed": 0},
        "by_severity": {"low": 0, "medium": 0, "high": 0, "critical": 0},
        "total":       0,
    }

    for row in results:
        status   = row.status   or "pending"
        severity = row.severity or "medium"
        count    = row.count

        if status in stats["by_status"]:
            stats["by_status"][status] += count
        if severity in stats["by_severity"]:
            stats["by_severity"][severity] += count
        stats["total"] += count

    return stats


def update_incident_status(
    db: Session, incident_id: int, status: str
) -> Optional[Dict[str, Any]]:
    """
    Updates incident status ('approved' or 'dismissed').
    Returns the updated incident dict or None if not found.
    """
    from models.tables import Incident
    from datetime import datetime

    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        return None

    incident.status = status
    if status == "approved":
        incident.approved_at = datetime.utcnow()

    try:
        db.commit()
        db.refresh(incident)
        logger.info(f"Incident {incident_id} status → {status}")
        return _serialise_incident(incident)
    except Exception as exc:
        db.rollback()
        logger.error(f"Failed to update incident {incident_id}: {exc}")
        return None


def create_incident(
    db: Session,
    description: str,
    snapshot: str = None,
    severity: str = "medium",
    incident_type: str = "anomaly",
) -> Optional[Dict[str, Any]]:
    """Creates a new incident record and returns the serialised dict."""
    from models.tables import Incident

    incident = Incident(
        type        = incident_type,
        severity    = severity,
        description = description,
        snapshot    = snapshot,
        status      = "pending",
    )
    try:
        db.add(incident)
        db.commit()
        db.refresh(incident)
        return _serialise_incident(incident)
    except Exception as exc:
        db.rollback()
        logger.error(f"Failed to create incident: {exc}")
        return None


# ── Snapshot Cleanup ──────────────────────────────────────────────────────────

def cleanup_old_snapshots(keep_last: int = 20) -> None:
    """Removes oldest snapshot files, keeping only the `keep_last` most recent."""
    # Guard: do nothing if path doesn't exist
    if not os.path.isdir(SNAPSHOTS_PATH):
        return

    try:
        files = [
            f for f in os.listdir(SNAPSHOTS_PATH)
            if f.lower().endswith((".jpg", ".jpeg", ".png"))
        ]
        files.sort(key=lambda f: os.path.getmtime(os.path.join(SNAPSHOTS_PATH, f)))

        if len(files) > keep_last:
            for f in files[:-keep_last]:
                try:
                    os.remove(os.path.join(SNAPSHOTS_PATH, f))
                except OSError as exc:
                    logger.warning(f"Could not delete snapshot {f}: {exc}")
    except Exception as exc:
        logger.error(f"cleanup_old_snapshots failed: {exc}")