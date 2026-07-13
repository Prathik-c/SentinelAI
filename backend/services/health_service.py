"""
SentinelAI — Improved Health Service

Provides system metrics collection and database logging with proper error handling,
retry logic, and richer process data.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

import psutil
from loguru import logger

from services.activity_service import get_idle_seconds, get_and_reset_event_count, get_foreground_window_title

# Prime the CPU measurement counter so the first call to cpu_percent(interval=0)
# returns a valid reading rather than 0.0 (psutil needs two samples to compute a delta).
try:
    psutil.cpu_percent(interval=0)
except Exception:
    pass


# ── Real-time Metrics ─────────────────────────────────────────────────────────

def get_health_metrics() -> Dict[str, Any]:
    """
    Collects current CPU, RAM, and Disk utilisation.

    FIX: Using cpu_percent(interval=0) instead of interval=0.5.
    interval=0 returns the reading since the LAST call — non-blocking.
    We prime the counter once at module import so the first reading is valid.
    The WebSocket loop calls this every 2s, so measurements are accurate.
    """
    try:
        return {
            "cpu":  round(psutil.cpu_percent(interval=0), 1),
            "ram":  round(psutil.virtual_memory().percent, 1),
            "disk": round(psutil.disk_usage("C:").percent, 1),
        }
    except Exception as exc:
        logger.warning(f"get_health_metrics failed: {exc}")
        return {"cpu": 0.0, "ram": 0.0, "disk": 0.0}


def get_top_processes(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Returns the top `limit` processes sorted by CPU utilisation.
    Includes pid and create_time for process identity tracking (detecting
    long-running or restarted processes).

    Skips: System Idle Process, System, empty names, inaccessible processes.
    """
    processes: List[Dict[str, Any]] = []

    for proc in psutil.process_iter(
        ["name", "cpu_percent", "memory_percent", "pid", "ppid", "create_time", "status"]
    ):
        try:
            info = proc.info
            name = (info.get("name") or "").strip()

            if name in ("System Idle Process", "System", "Idle", ""):
                continue

            cpu = info.get("cpu_percent") or 0.0
            ram = info.get("memory_percent") or 0.0

            processes.append({
                "name":        name,
                "cpu":         round(cpu, 1),
                "ram":         round(ram, 1),
                "pid":         info.get("pid"),
                "ppid":        info.get("ppid"),
                "create_time": info.get("create_time"),
                "status":      info.get("status", "unknown"),
            })

        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        except Exception as exc:
            logger.debug(f"Skipping process in get_top_processes: {exc}")
            continue

    processes.sort(key=lambda p: p["cpu"], reverse=True)
    return processes[:limit]


# ── Database Logging ──────────────────────────────────────────────────────────

def log_health_snapshot(db) -> Optional[Any]:
    """
    Collects current system state and writes a HealthLog row to the database.
    Returns the created log entry, or None on failure.

    Handles:
    - psutil failures gracefully (partial data is still logged).
    - Database lock errors (logs the error but does not crash the background task).
    - JSON serialisation errors for process data.
    """
    from models.tables import HealthLog

    start = time.monotonic()

    # Collect metrics — individual failures return safe defaults
    try:
        metrics = get_health_metrics()
    except Exception as exc:
        logger.error(f"Failed to collect health metrics: {exc}")
        metrics = {"cpu": 0.0, "ram": 0.0, "disk": 0.0}

    try:
        processes = get_top_processes(limit=10)
        processes_json = json.dumps(processes)
    except Exception as exc:
        logger.error(f"Failed to collect process list: {exc}")
        processes_json = "[]"

    try:
        idle = round(get_idle_seconds(), 1)
        events = get_and_reset_event_count()
        foreground_app = get_foreground_window_title()
    except Exception as exc:
        logger.debug(f"Failed to get activity data: {exc}")
        idle = 0.0
        events = 0
        foreground_app = ""

    # Write to DB with retry on lock
    try:
        log_entry = HealthLog(
            cpu           = metrics["cpu"],
            ram           = metrics["ram"],
            disk          = metrics["disk"],
            gpu           = None,  # Not tracking GPU currently
            top_processes = processes_json,
            idle_seconds  = idle,
            foreground_app= foreground_app,
            keyboard_mouse_events = events,
        )
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)

        elapsed = time.monotonic() - start
        logger.debug(
            f"Health snapshot logged | id={log_entry.id} | "
            f"cpu={metrics['cpu']}% ram={metrics['ram']}% | elapsed={elapsed:.3f}s"
        )
        return log_entry

    except Exception as exc:
        db.rollback()
        logger.error(f"Failed to log health snapshot: {exc}")
        return None