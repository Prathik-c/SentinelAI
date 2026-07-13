"""
SentinelAI — System Status Router

Provides operational transparency: LLM availability, DB health, uptime,
background task status, and version info.
"""
from __future__ import annotations

import os
import time
from datetime import datetime

from fastapi import APIRouter, Depends
from loguru import logger
from sqlalchemy.orm import Session

from config import (
    CHAT_MODEL,
    DB_PATH,
    OLLAMA_BASE_URL,
    REPORT_MODEL,
)
from database import get_db

router = APIRouter(prefix="/system", tags=["System"])

# Application start time (set when module is imported at startup)
_start_time = time.time()


@router.get("/status")
async def system_status(db: Session = Depends(get_db)):
    """
    Returns overall SentinelAI operational status:
    - DB health (record counts, DB file size)
    - LLM availability (can we reach Ollama?)
    - Uptime
    - Baseline readiness
    """
    uptime_seconds = int(time.time() - _start_time)

    # ── DB health ──────────────────────────────────────────────────────────
    db_health = {"status": "ok"}
    try:
        from models.tables import HealthLog, Incident, ChatHistory
        db_health["health_log_count"] = db.query(HealthLog).count()
        db_health["incident_count"]   = db.query(Incident).count()
        db_health["chat_count"]       = db.query(ChatHistory).count()
        db_size = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
        db_health["db_size_mb"] = round(db_size / 1024 / 1024, 2)
    except Exception as exc:
        logger.warning(f"DB health check failed: {exc}")
        db_health = {"status": "error", "detail": str(exc)}

    # ── LLM availability (non-blocking async HTTP) ─────────────────────
    llm_status = {"status": "unknown"}
    try:
        import asyncio, httpx
        async def _check():
            async with httpx.AsyncClient(timeout=3.0) as c:
                r = await c.get(f"{OLLAMA_BASE_URL}/api/tags")
                return r
        response = await asyncio.wait_for(_check(), timeout=3.5)
        if response.status_code == 200:
            models = [m["name"] for m in response.json().get("models", [])]
            llm_status = {
                "status":        "online",
                "available_models": models,
                "chat_model":    CHAT_MODEL,
                "report_model":  REPORT_MODEL,
                "chat_model_ready":   CHAT_MODEL in models,
                "report_model_ready": REPORT_MODEL in models,
            }
        else:
            llm_status = {"status": "error", "code": response.status_code}
    except Exception:
        llm_status = {
            "status": "offline",
            "detail": f"Cannot reach Ollama at {OLLAMA_BASE_URL}",
        }

    # ── Baseline readiness ──────────────────────────────────────────────────
    baseline_status = {"ready": False}
    try:
        from services.baseline_engine import get_cached_baseline
        bl = get_cached_baseline(db)
        baseline_status = {
            "ready":        True,
            "sample_count": bl.sample_count,
            "computed_at":  bl.computed_at,
        }
    except Exception:
        baseline_status = {"ready": False}

    return {
        "service":       "SentinelAI",
        "version":       "2.0.0",
        "status":        "running",
        "uptime_seconds": uptime_seconds,
        "uptime_human":  _format_uptime(uptime_seconds),
        "timestamp":     datetime.utcnow().isoformat(),
        "database":      db_health,
        "llm":           llm_status,
        "baseline":      baseline_status,
    }


@router.get("/version")
def version():
    """Returns version information."""
    return {
        "version":   "2.0.0",
        "name":      "SentinelAI",
        "build":     "production-refactor",
        "ollama_url": OLLAMA_BASE_URL,
        "models": {
            "chat":   CHAT_MODEL,
            "report": REPORT_MODEL,
        },
    }


@router.get("/llm")
def llm_diagnostics():
    """
    Returns real-time LLM operational diagnostics.

    Unlike /system/status, this endpoint NEVER makes an HTTP call to Ollama.
    It reads only the in-memory state of the singleton ollama_client module.
    Safe to poll frequently from the frontend.

    Returns:
      model          — the loaded model name
      model_warmed   — True if warm-up completed successfully at startup
      total_calls    — lifetime inference request count
      total_errors   — lifetime timeout/error count
      last_latency_ms — most recent inference latency
      active_calls   — calls currently being generated
      max_concurrent — semaphore capacity
      ollama_process_mem_mb — RAM used by the ollama process
    """
    try:
        from services.ollama_client import get_llm_status
        return get_llm_status()
    except Exception as exc:
        logger.warning(f"LLM diagnostics unavailable: {exc}")
        return {"status": "unavailable", "detail": str(exc)}


def _format_uptime(seconds: int) -> str:
    days    = seconds // 86400
    hours   = (seconds % 86400) // 3600
    minutes = (seconds % 3600)  // 60
    parts   = []
    if days:    parts.append(f"{days}d")
    if hours:   parts.append(f"{hours}h")
    if minutes: parts.append(f"{minutes}m")
    parts.append(f"{seconds % 60}s")
    return " ".join(parts)
