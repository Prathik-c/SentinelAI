"""
SentinelAI — Background Task Scheduler

Centralises all recurring background tasks:
  - periodic_health_logger:   every 60s  — log health snapshot to DB
  - periodic_anomaly_checker: every 5min — run anomaly detection pipeline
  - periodic_baseline_updater: every 1hr — recompute and persist baseline
  - periodic_weekly_reporter:  every 7d  — generate weekly report

Design principles:
  - Each task is completely isolated: a crash in one never affects others.
  - Each task logs its own timing and error details.
  - All tasks use their own DB sessions (never share sessions across tasks).
  - No task directly calls the LLM inline (LLM is async background work only).
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta

from loguru import logger

from config import (
    ANOMALY_CHECK_INTERVAL,
    BASELINE_UPDATE_INTERVAL,
    LOG_INTERVAL,
    REPORT_INTERVAL_DAYS,
)


# ── Task: Health Snapshot Logger ──────────────────────────────────────────────

async def periodic_health_logger() -> None:
    """
    Logs a health snapshot to the DB every LOG_INTERVAL seconds.
    Uses its own fresh DB session per iteration.
    Never crashes the entire scheduler — errors are logged and retried next cycle.
    """
    logger.info(f"Health logger started | interval={LOG_INTERVAL}s")

    while True:
        try:
            from database import SessionLocal
            from services.health_service import log_health_snapshot

            db = SessionLocal()
            try:
                entry = log_health_snapshot(db)
                if entry:
                    logger.debug(f"Health snapshot logged | id={entry.id}")
            finally:
                db.close()

        except Exception as exc:
            logger.error(f"periodic_health_logger error: {exc}")

        await asyncio.sleep(LOG_INTERVAL)


# ── Task: Anomaly Checker ─────────────────────────────────────────────────────

async def periodic_anomaly_checker() -> None:
    """
    Runs the full anomaly detection pipeline every ANOMALY_CHECK_INTERVAL seconds.
    This is pure Python detection (< 100ms) — the LLM explanation is scheduled
    as a separate background task by incident_engine.
    """
    logger.info(f"Anomaly checker started | interval={ANOMALY_CHECK_INTERVAL}s")

    while True:
        await asyncio.sleep(ANOMALY_CHECK_INTERVAL)  # Wait first on startup
        start = time.monotonic()

        try:
            from database import SessionLocal
            from services.incident_engine import run_anomaly_check

            db = SessionLocal()
            try:
                result = run_anomaly_check(db)
                elapsed = time.monotonic() - start
                logger.info(
                    f"Background anomaly check | status={result.get('status')} "
                    f"| found={result.get('anomaly_count', 0)} "
                    f"| saved={result.get('incidents_saved', 0)} "
                    f"| elapsed={elapsed:.3f}s"
                )
            finally:
                db.close()

        except Exception as exc:
            logger.error(f"periodic_anomaly_checker error: {exc}")


# ── Task: Baseline Updater ────────────────────────────────────────────────────

async def periodic_baseline_updater() -> None:
    """
    Recomputes the behavioural baseline every BASELINE_UPDATE_INTERVAL seconds
    and persists it to the BaselineSnapshot table. Also invalidates the in-memory
    cache so the next anomaly check uses fresh data.
    """
    logger.info(f"Baseline updater started | interval={BASELINE_UPDATE_INTERVAL}s")

    while True:
        await asyncio.sleep(BASELINE_UPDATE_INTERVAL)  # Wait first on startup
        start = time.monotonic()

        try:
            from database import SessionLocal
            from services.baseline_engine import (
                compute_baseline,
                invalidate_cache,
                persist_baseline,
            )

            db = SessionLocal()
            try:
                stats = compute_baseline(db)
                persist_baseline(db, stats)
                invalidate_cache()
                elapsed = time.monotonic() - start
                logger.info(
                    f"Baseline updated | samples={stats.sample_count} "
                    f"| cpu_mean={stats.cpu_mean}% | elapsed={elapsed:.3f}s"
                )
            finally:
                db.close()

        except Exception as exc:
            logger.error(f"periodic_baseline_updater error: {exc}")


# ── Task: Weekly Reporter ─────────────────────────────────────────────────────

async def periodic_weekly_reporter() -> None:
    """
    Generates the weekly system health report every REPORT_INTERVAL_DAYS days.
    Uses its own session, is fully isolated from other tasks.
    """
    interval_seconds = REPORT_INTERVAL_DAYS * 86400
    logger.info(
        f"Weekly reporter started | interval={REPORT_INTERVAL_DAYS} days"
    )

    while True:
        await asyncio.sleep(interval_seconds)
        start = time.monotonic()

        try:
            from database import SessionLocal
            from services.report_engine import generate_weekly_report

            db = SessionLocal()
            try:
                result = await generate_weekly_report(db, days=REPORT_INTERVAL_DAYS)
                elapsed = time.monotonic() - start
                logger.info(
                    f"Weekly report generated | id={result.get('report_id')} "
                    f"| health={result.get('health_score')} "
                    f"| risk={result.get('risk_score')} "
                    f"| elapsed={elapsed:.2f}s"
                )
            finally:
                db.close()

        except Exception as exc:
            logger.error(f"periodic_weekly_reporter error: {exc}")


# ── Scheduler Entry Point ─────────────────────────────────────────────────────

def start_all_background_tasks() -> None:
    """
    Schedules all background tasks as asyncio tasks.
    Must be called from within an async context (e.g., FastAPI startup event).
    """
    tasks = [
        ("HealthLogger",      periodic_health_logger()),
        ("AnomalyChecker",    periodic_anomaly_checker()),
        ("BaselineUpdater",   periodic_baseline_updater()),
        ("WeeklyReporter",    periodic_weekly_reporter()),
    ]

    for name, coro in tasks:
        task = asyncio.create_task(coro, name=name)
        task.add_done_callback(
            lambda t: logger.error(
                f"Background task '{t.get_name()}' exited unexpectedly: "
                f"{t.exception()}"
            ) if not t.cancelled() and t.exception() else None
        )
        logger.info(f"Background task started: {name}")
