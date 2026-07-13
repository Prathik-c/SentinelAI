"""
SentinelAI — Incident Engine

Orchestrates the full anomaly-detection-to-persistence pipeline:

  1. Get current metrics (health_service)
  2. Get or recompute baseline (baseline_engine, cached)
  3. Run pure-Python anomaly detection (anomaly_engine) → List[IncidentData]
  4. Deduplicate against recent DB records (5-minute window per type)
  5. Persist new incidents immediately (no LLM needed)
  6. Trigger async LLM explanation for each new incident
  7. Update incident.report in DB when LLM finishes

Why this matters:
- Anomaly detection returns in < 100ms (pure Python).
- The API endpoint returns structured incidents immediately.
- LLM explanations fill in asynchronously — UI shows "Loading explanation..."
  until the LLM is done, without blocking the user.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy.orm import Session

from config import MIN_BASELINE_SAMPLES
from core.exceptions import BaselineNotReadyError
from services.anomaly_engine import detect_anomalies
from services.analyzers.base import IncidentData
from services.baseline_engine import get_cached_baseline
from services.health_service import get_health_metrics, get_top_processes
from services.llm_service import explain_incident_async


# ── Deduplication ─────────────────────────────────────────────────────────────

def _is_duplicate(
    db: Session,
    incident_type: str,
    process_name: Optional[str],
    window_minutes: int = 5,
) -> bool:
    """
    Returns True if a pending incident of the same type (and process, if applicable)
    was already logged within the last `window_minutes`.

    Prevents alert flooding when an anomaly condition persists across multiple
    successive anomaly checks.
    """
    from models.tables import Incident

    cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)
    query = (
        db.query(Incident)
        .filter(
            Incident.type == incident_type,
            Incident.status == "pending",
            Incident.timestamp >= cutoff,
        )
    )
    if process_name:
        query = query.filter(Incident.process_name == process_name)

    return query.first() is not None


# ── Async LLM backfill ────────────────────────────────────────────────────────

async def _backfill_explanation(incident_id: int, incident_dict: Dict[str, Any]) -> None:
    """
    Calls the LLM to explain an incident and writes the result back to the DB.
    Runs as a background asyncio task — does not block the route handler.
    """
    from database import SessionLocal

    logger.debug(f"Starting LLM backfill for incident id={incident_id}")
    try:
        explanation = await explain_incident_async(incident_dict)
    except Exception as exc:
        logger.error(f"LLM backfill failed for incident {incident_id}: {exc}")
        return

    # Write explanation back to DB in a fresh session
    db = SessionLocal()
    try:
        from models.tables import Incident as IncidentModel
        incident = db.query(IncidentModel).filter(IncidentModel.id == incident_id).first()
        if incident:
            incident.report = explanation
            db.commit()
            logger.debug(f"Explanation saved | incident_id={incident_id}")
    except Exception as exc:
        db.rollback()
        logger.error(f"Failed to save LLM explanation for incident {incident_id}: {exc}")
    finally:
        db.close()


# ── Main Pipeline ─────────────────────────────────────────────────────────────

def run_anomaly_check(db: Session) -> Dict[str, Any]:
    """
    Full anomaly detection pipeline. Returns structured results immediately.
    LLM explanations are filled in asynchronously in the background.

    Returns:
        {
          "status": "normal" | "learning" | "anomalies_found",
          "baseline_samples": int,
          "your_normal": {...},
          "anomaly_count": int,
          "anomalies": [IncidentData.to_dict(), ...],
          "incidents_saved": int,
          "message": str,
        }
    """
    start = time.monotonic()

    # ── Step 1: Get baseline ────────────────────────────────────────────────
    try:
        baseline = get_cached_baseline(db)
    except BaselineNotReadyError as exc:
        logger.info(f"Anomaly check skipped: {exc.message}")
        return {
            "status":           "learning",
            "message":          exc.message,
            "baseline_samples": exc.current,
            "anomaly_count":    0,
            "anomalies":        [],
            "incidents_saved":  0,
        }
    except Exception as exc:
        logger.error(f"Baseline computation failed: {exc}")
        return {
            "status":  "error",
            "message": "Failed to compute baseline. Check logs for details.",
            "anomaly_count": 0,
            "anomalies": [],
            "incidents_saved": 0,
        }

    # ── Step 2: Get current metrics ─────────────────────────────────────────
    metrics   = get_health_metrics()
    processes = get_top_processes(limit=10)

    # ── Step 3: Detect anomalies (pure Python) ──────────────────────────────
    from services.activity_service import get_idle_seconds, get_and_reset_event_count, get_foreground_window_title
    try:
        idle = get_idle_seconds()
        events = get_and_reset_event_count()
        app = get_foreground_window_title()
    except Exception:
        idle = 0.0
        events = 0
        app = ""

    detected: List[IncidentData] = detect_anomalies(
        cpu           = metrics["cpu"],
        ram           = metrics["ram"],
        disk          = metrics["disk"],
        idle_seconds  = idle,
        top_processes = processes,
        baseline      = baseline,
        keyboard_mouse_events = events,
        foreground_app = app,
        db_session     = db,
    )

    # ── Step 4 & 5: Deduplicate and persist ─────────────────────────────────
    from models.tables import Incident as IncidentModel

    saved_incidents: List[Dict[str, Any]] = []

    for inc in detected:
        if _is_duplicate(db, inc.incident_type, inc.process_name):
            logger.debug(
                f"Duplicate incident skipped | type={inc.incident_type} "
                f"process={inc.process_name}"
            )
            continue

        try:
            db_incident = IncidentModel(
                type         = inc.incident_type,
                severity     = inc.severity,
                description  = inc.description,
                process_name = inc.process_name,
                risk_score   = inc.risk_score,
                reasons      = json.dumps(inc.reasons),
                snapshot     = json.dumps(inc.snapshot or {}),
                status       = "pending",
                report       = None,  # Will be filled by LLM async
            )
            db.add(db_incident)
            db.flush()  # Get the ID without full commit yet
            saved_id = db_incident.id
            db.commit()

            inc_dict = inc.to_dict()
            inc_dict["id"] = saved_id
            saved_incidents.append(inc_dict)

            logger.info(
                f"Incident saved | id={saved_id} | type={inc.incident_type} "
                f"| severity={inc.severity} | risk={inc.risk_score}"
            )

            # ── Step 6: Schedule async LLM backfill ─────────────────────────
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(_backfill_explanation(saved_id, inc_dict))
                else:
                    # Background task context — skip LLM for now
                    pass
            except RuntimeError:
                pass  # No event loop in background thread — OK, will skip LLM

        except Exception as exc:
            db.rollback()
            logger.error(f"Failed to save incident | type={inc.incident_type}: {exc}")

    elapsed = time.monotonic() - start

    baseline_context = {
        "cpu_mean":         baseline.cpu_mean,
        "ram_mean":         baseline.ram_mean,
        "cpu_threshold":    baseline.cpu_threshold,
        "ram_threshold":    baseline.ram_threshold,
        "baseline_samples": baseline.sample_count,
    }

    all_anomaly_dicts = [inc.to_dict() for inc in detected]

    logger.info(
        f"Anomaly check complete | detected={len(detected)} "
        f"| saved={len(saved_incidents)} | elapsed={elapsed:.3f}s"
    )

    return {
        "status":           "anomalies_found" if detected else "normal",
        "baseline_samples": baseline.sample_count,
        "your_normal":      baseline_context,
        "anomaly_count":    len(detected),
        "anomalies":        all_anomaly_dicts,
        "incidents_saved":  len(saved_incidents),
        "message":          (
            f"Detected {len(detected)} anomalies." if detected
            else "System behaviour is within normal parameters."
        ),
        "explanation": (
            "AI explanations are being generated and will appear in the Alerts panel shortly."
            if saved_incidents else
            "✅ System is operating normally within your established baseline."
        ),
    }
