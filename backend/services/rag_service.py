"""
SentinelAI — Intelligent RAG Service

Implements intent-aware retrieval-augmented generation:
  1. Classify question intent (instant, keyword-based)
  2. Execute targeted DB query (only relevant data)
  3. Format minimal, token-efficient context
  4. Call LLM asynchronously with timeout

This is fundamentally different from the old approach of always dumping
the same 20+10 rows into the prompt regardless of the question.

Token efficiency:
  Old approach: ~20 rows × ~80 chars = ~1,600 chars → ~400 tokens per query
  New approach: ~5-10 rows × relevant fields only = ~400 chars → ~100 tokens per query
  Result: ~4x reduction in prompt size → ~4x faster LLM responses
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Optional, Tuple

from loguru import logger
from sqlalchemy.orm import Session

from config import MAX_LOG_CONTEXT_ROWS
from services.intent_classifier import (
    Intent,
    classify,
    extract_process_name,
    extract_time_window,
)


# ── Context Formatters ────────────────────────────────────────────────────────

def _format_log_row(log, fields: str = "all") -> str:
    """
    Formats a single HealthLog row as a compact context string.

    Args:
        log: HealthLog ORM object.
        fields: "all" | "cpu" | "ram" | "disk" | "processes"
    """
    ts = str(log.timestamp)[:16]  # "YYYY-MM-DD HH:MM"

    if fields == "cpu":
        procs = _top_procs_str(log, n=3, metric="cpu")
        return f"[{ts}] CPU={log.cpu:.1f}% | top: {procs}"

    if fields == "ram":
        return f"[{ts}] RAM={log.ram:.1f}% | CPU={log.cpu:.1f}%"

    if fields == "disk":
        return f"[{ts}] Disk={log.disk:.1f}%"

    if fields == "processes":
        procs = _top_procs_str(log, n=5, metric="cpu")
        return f"[{ts}] Processes: {procs}"

    # "all" — compact representation
    procs = _top_procs_str(log, n=3, metric="cpu")
    idle  = f" idle={log.idle_seconds:.0f}s" if log.idle_seconds else ""
    return f"[{ts}] CPU={log.cpu:.1f}% RAM={log.ram:.1f}% Disk={log.disk:.1f}%{idle} | {procs}"


def _top_procs_str(log, n: int = 3, metric: str = "cpu") -> str:
    """Formats the top N processes from a HealthLog row as a compact string."""
    if not log.top_processes:
        return "(no process data)"
    try:
        procs = json.loads(log.top_processes)
        # Sort by the requested metric
        procs = sorted(procs, key=lambda p: p.get(metric, 0), reverse=True)
        return ", ".join(
            f"{p.get('name', '?')}({p.get(metric, 0):.1f}%)"
            for p in procs[:n]
        )
    except (json.JSONDecodeError, TypeError, KeyError):
        return "(malformed process data)"


# ── Targeted Retrievers ───────────────────────────────────────────────────────

def _fetch_ram_context(db: Session, question: str) -> str:
    """Returns RAM-relevant logs: recent spikes and general recent readings."""
    from models.tables import HealthLog
    from services.intent_classifier import extract_time_window

    time_window = extract_time_window(question)
    
    spike_query = db.query(HealthLog).filter(HealthLog.ram > 80)
    recent_query = db.query(HealthLog)
    
    time_str = " RECENTLY"
    if time_window:
        start_dt, end_dt = time_window
        spike_query = spike_query.filter(HealthLog.timestamp >= start_dt, HealthLog.timestamp <= end_dt)
        recent_query = recent_query.filter(HealthLog.timestamp >= start_dt, HealthLog.timestamp <= end_dt)
        time_str = f" FROM {start_dt.strftime('%Y-%m-%d %H:%M')} TO {end_dt.strftime('%Y-%m-%d %H:%M')}"

    high_ram = spike_query.order_by(HealthLog.timestamp.desc()).limit(MAX_LOG_CONTEXT_ROWS).all()
    recent = recent_query.order_by(HealthLog.timestamp.desc()).limit(5).all()

    lines = [f"RAM USAGE HISTORY (high-RAM events){time_str}:"]
    if high_ram:
        for log in high_ram:
            lines.append(_format_log_row(log, "ram"))
    else:
        if time_window and "today" in question.lower():
            lines.append("No RAM spikes > 80% detected today.")
        else:
            lines.append("No RAM spikes > 80% found in this time period.")

    lines.append("\nGENERAL READINGS:")
    if recent:
        for log in recent:
            lines.append(_format_log_row(log, "ram"))
    else:
        lines.append("No data available.")

    return "\n".join(lines)


def _fetch_cpu_context(db: Session, question: str) -> str:
    """Returns CPU and process-relevant logs."""
    from models.tables import HealthLog
    from services.intent_classifier import extract_time_window

    query = db.query(HealthLog)
    time_window = extract_time_window(question)
    time_str = " (most recent first)"
    if time_window:
        start_dt, end_dt = time_window
        query = query.filter(HealthLog.timestamp >= start_dt, HealthLog.timestamp <= end_dt)
        time_str = f" FROM {start_dt.strftime('%Y-%m-%d %H:%M')} TO {end_dt.strftime('%Y-%m-%d %H:%M')}"

    recent = query.order_by(HealthLog.timestamp.desc()).limit(MAX_LOG_CONTEXT_ROWS).all()

    lines = [f"CPU & PROCESS HISTORY{time_str}:"]
    if recent:
        for log in recent:
            lines.append(_format_log_row(log, "cpu"))
    else:
        lines.append("No data available for this time period.")
        
    return "\n".join(lines)


def _fetch_disk_context(db: Session, question: str) -> str:
    """Returns disk-relevant logs."""
    from models.tables import HealthLog
    from services.intent_classifier import extract_time_window

    query = db.query(HealthLog)
    time_window = extract_time_window(question)
    time_str = " (most recent first)"
    if time_window:
        start_dt, end_dt = time_window
        query = query.filter(HealthLog.timestamp >= start_dt, HealthLog.timestamp <= end_dt)
        time_str = f" FROM {start_dt.strftime('%Y-%m-%d %H:%M')} TO {end_dt.strftime('%Y-%m-%d %H:%M')}"

    recent = query.order_by(HealthLog.timestamp.desc()).limit(MAX_LOG_CONTEXT_ROWS).all()

    lines = [f"DISK USAGE HISTORY{time_str}:"]
    if recent:
        for log in recent:
            lines.append(_format_log_row(log, "disk"))
    else:
        lines.append("No data available for this time period.")
        
    return "\n".join(lines)


def _fetch_time_context(
    db: Session, question: str
) -> str:
    """Returns logs within the time window extracted from the question."""
    from models.tables import HealthLog

    window = extract_time_window(question, window_minutes=30)
    if window is None:
        # Fallback: last 24h if we couldn't parse a specific time
        end   = datetime.utcnow()
        start = end - timedelta(hours=24)
    else:
        start, end = window

    logs = (
        db.query(HealthLog)
        .filter(HealthLog.timestamp >= start, HealthLog.timestamp <= end)
        .order_by(HealthLog.timestamp.asc())
        .limit(MAX_LOG_CONTEXT_ROWS)
        .all()
    )

    lines = [
        f"LOGS FROM {start.strftime('%Y-%m-%d %H:%M')} "
        f"TO {end.strftime('%Y-%m-%d %H:%M')} UTC:"
    ]
    if logs:
        for log in logs:
            lines.append(_format_log_row(log, "all"))
    else:
        lines.append("No system logs found for this time window.")

    return "\n".join(lines)


def _fetch_process_context(db: Session, question: str) -> str:
    """Returns logs containing a specific process name."""
    from models.tables import HealthLog
    from services.intent_classifier import extract_time_window

    proc_name = extract_process_name(question)
    time_window = extract_time_window(question)
    
    query = db.query(HealthLog)
    time_str = ""
    if time_window:
        start_dt, end_dt = time_window
        query = query.filter(HealthLog.timestamp >= start_dt, HealthLog.timestamp <= end_dt)
        time_str = f" FROM {start_dt.strftime('%Y-%m-%d %H:%M')} TO {end_dt.strftime('%Y-%m-%d %H:%M')}"

    recent = query.order_by(HealthLog.timestamp.desc()).limit(50).all()  # Search wider, filter in Python

    lines = []
    matching_logs = []

    for log in recent:
        if not log.top_processes:
            continue
        try:
            procs = json.loads(log.top_processes)
        except json.JSONDecodeError:
            continue

        # Filter by process name if extracted, otherwise show top processes
        if proc_name:
            relevant = [
                p for p in procs
                if proc_name.lower() in p.get("name", "").lower()
            ]
        else:
            relevant = procs[:3]

        if relevant:
            proc_str = ", ".join(
                f"{p.get('name')}(cpu={p.get('cpu'):.1f}% ram={p.get('ram'):.1f}%)"
                for p in relevant
            )
            matching_logs.append(
                f"[{str(log.timestamp)[:16]}] {proc_str}"
            )

        if len(matching_logs) >= MAX_LOG_CONTEXT_ROWS:
            break

    header = (
        f"LOGS FOR PROCESS '{proc_name}'{time_str}:" if proc_name
        else f"TOP PROCESS HISTORY{time_str}:"
    )
    lines = [header]
    if matching_logs:
        lines.extend(matching_logs)
    else:
        lines.append(
            f"No logs found containing '{proc_name}' in this time period." if proc_name
            else "No process data available for this time period."
        )

    return "\n".join(lines)


def _fetch_incident_context(db: Session, question: str) -> str:
    """Returns recent incidents/alerts, optionally filtered by time."""
    from models.tables import Incident
    from services.intent_classifier import extract_time_window

    query = db.query(Incident).order_by(Incident.timestamp.desc())

    time_window = extract_time_window(question)
    time_context_str = ""
    if time_window:
        start_dt, end_dt = time_window
        query = query.filter(Incident.timestamp >= start_dt, Incident.timestamp <= end_dt)
        time_context_str = f" from {start_dt.strftime('%Y-%m-%d %H:%M')} to {end_dt.strftime('%Y-%m-%d %H:%M')}"

    # Limit to 5 (down from 10) to keep prompt small enough for Mistral 7B to answer quickly
    incidents = query.limit(5).all()

    lines = [f"DETECTED ANOMALIES & INCIDENTS{time_context_str.upper()}:"]
    if incidents:
        for inc in incidents:
            reasons = ""
            if inc.reasons:
                try:
                    r = json.loads(inc.reasons)
                    reasons = " | ".join(r[:2]) if r else ""
                except json.JSONDecodeError:
                    reasons = ""
            lines.append(
                f"[{str(inc.timestamp)[:16]}] [{inc.severity.upper()}] "
                f"{inc.type}: {inc.description}"
                + (f" — {reasons}" if reasons else "")
            )
    else:
        if time_window and "today" in question.lower():
            lines.append("No anomalies were detected today.")
        else:
            lines.append("No incidents recorded for this time period.")

    return "\n".join(lines)


def _fetch_health_check_context(db: Session, question: str) -> str:
    """Returns a compact health overview: latest 5 logs + baseline stats."""
    from models.tables import HealthLog
    from services.intent_classifier import extract_time_window

    query = db.query(HealthLog)
    time_window = extract_time_window(question)
    time_str = ""
    if time_window:
        start_dt, end_dt = time_window
        query = query.filter(HealthLog.timestamp >= start_dt, HealthLog.timestamp <= end_dt)
        time_str = f" FROM {start_dt.strftime('%Y-%m-%d %H:%M')} TO {end_dt.strftime('%Y-%m-%d %H:%M')}"

    recent = query.order_by(HealthLog.timestamp.desc()).limit(5).all()

    lines = [f"SYSTEM READINGS{time_str}:"]
    if recent:
        for log in recent:
            lines.append(_format_log_row(log, "all"))
    else:
        lines.append("No data available for this time period.")

    # Append quick baseline summary
    try:
        from services.baseline_engine import get_cached_baseline
        bl = get_cached_baseline(db)
        lines.append(
            f"\nYOUR BASELINE (from {bl.sample_count} samples): "
            f"avg CPU={bl.cpu_mean:.1f}% "
            f"avg RAM={bl.ram_mean:.1f}% "
            f"avg Disk={bl.disk_mean:.1f}%"
        )
    except Exception:
        pass  # Baseline may not be ready — OK

    return "\n".join(lines)


def _fetch_general_context(db: Session, question: str) -> str:
    """General fallback: last 10 logs + recent incidents."""
    from models.tables import HealthLog, Incident
    from services.intent_classifier import extract_time_window

    log_query = db.query(HealthLog)
    inc_query = db.query(Incident)
    time_window = extract_time_window(question)
    time_str = "RECENT"
    if time_window:
        start_dt, end_dt = time_window
        log_query = log_query.filter(HealthLog.timestamp >= start_dt, HealthLog.timestamp <= end_dt)
        inc_query = inc_query.filter(Incident.timestamp >= start_dt, Incident.timestamp <= end_dt)
        time_str = f"ACTIVITY FROM {start_dt.strftime('%Y-%m-%d %H:%M')} TO {end_dt.strftime('%Y-%m-%d %H:%M')}"

    recent = log_query.order_by(HealthLog.timestamp.desc()).limit(MAX_LOG_CONTEXT_ROWS).all()
    incidents = inc_query.order_by(Incident.timestamp.desc()).limit(5).all()

    lines = [f"{time_str} SYSTEM ACTIVITY:"]
    if recent:
        for log in recent:
            lines.append(_format_log_row(log, "all"))
    else:
        lines.append("No system logs found for this time period.")

    if incidents:
        lines.append("\nALERTS IN THIS PERIOD:")
        for inc in incidents:
            lines.append(
                f"[{str(inc.timestamp)[:16]}] "
                f"[{inc.severity.upper()}] {inc.type}: {inc.description}"
            )

    return "\n".join(lines)


# ── Fast-path responses (no DB, no LLM) ──────────────────────────────────────

_GREETING_RESPONSE = (
    "👋 Hi! I'm SentinelAI, your local system intelligence monitor. "
    "I'm watching your CPU, RAM, disk, and processes 24/7. "
    "Ask me anything — like 'any anomalies today?' or 'what's my CPU history?'"
)

_HELP_RESPONSE = (
    "🛡️ **SentinelAI — What I can answer:**\n\n"
    "• **Resource queries** — 'What was my RAM at 3 PM?' / 'Show my CPU history'\n"
    "• **Process queries** — 'What is chrome.exe doing?' / 'Which process uses most CPU?'\n"
    "• **Anomaly queries** — 'Any threats today?' / 'Explain the last alert'\n"
    "• **Time queries** — 'What happened last night?' / 'What was running 2 hours ago?'\n"
    "• **Live status** — 'Current CPU' / 'What's my RAM right now?'\n"
    "• **Weekly summary** — 'Give me a weekly report'\n\n"
    "All processing is **100% local** — your data never leaves this machine."
)


def _simple_status_response() -> str:
    """Returns live CPU/RAM/Disk without any DB query or LLM call."""
    try:
        from services.health_service import get_health_metrics
        m = get_health_metrics()
        return (
            f"📊 **Live System Status:**\n"
            f"• CPU: **{m['cpu']}%**\n"
            f"• RAM: **{m['ram']}%**\n"
            f"• Disk: **{m['disk']}%**\n\n"
            f"Ask me about historical trends or anomalies for deeper insight."
        )
    except Exception:
        return "Unable to read live metrics at this moment."


# ── Main Entry Point ──────────────────────────────────────────────────────────

async def answer_question(db, question: str) -> str:
    """
    End-to-end RAG pipeline with fast-path routing.

    Routing table:
      GREETING      → instant canned response (0ms, no DB, no LLM)
      HELP          → instant canned response (0ms, no DB, no LLM)
      SIMPLE_STATUS → live psutil call only   (<5ms, no DB, no LLM)
      All others    → targeted DB retrieval   + LLM generation

    Per-stage timing is logged separately so bottlenecks are visible.
    """
    import time
    t_start = time.monotonic()

    # Step 1: Classify intent (pure Python, always instant)
    intent = classify(question)
    t_classified = time.monotonic()

    logger.info(
        f"RAG | intent={intent} | classify={((t_classified-t_start)*1000):.1f}ms "
        f"| q='{question[:60]}'"
    )

    # ── Fast paths — return immediately, zero DB/LLM cost ────────────────────
    if intent == Intent.GREETING:
        logger.debug("Fast-path: GREETING")
        return _GREETING_RESPONSE

    if intent == Intent.HELP:
        logger.debug("Fast-path: HELP")
        return _HELP_RESPONSE

    if intent == Intent.SIMPLE_STATUS:
        logger.debug("Fast-path: SIMPLE_STATUS")
        return _simple_status_response()

    # ── RAG path — fetch context from DB, then call LLM ──────────────────────

    # Step 2: Targeted DB retrieval
    try:
        if intent == Intent.RAM_SPIKE:
            context = _fetch_ram_context(db, question)
        elif intent == Intent.CPU_QUERY:
            context = _fetch_cpu_context(db, question)
        elif intent == Intent.DISK_QUERY:
            context = _fetch_disk_context(db, question)
        elif intent == Intent.TIME_QUERY:
            context = _fetch_time_context(db, question)
        elif intent == Intent.PROCESS_QUERY:
            context = _fetch_process_context(db, question)
        elif intent == Intent.INCIDENT_QUERY:
            context = _fetch_incident_context(db, question)
        elif intent == Intent.HEALTH_CHECK:
            context = _fetch_health_check_context(db, question)
        else:
            context = _fetch_general_context(db, question)

        t_retrieved = time.monotonic()
        logger.debug(
            f"RAG | db_query={((t_retrieved-t_classified)*1000):.1f}ms "
            f"| context_chars={len(context)}"
        )

    except Exception as exc:
        logger.error(f"RAG context retrieval failed: {exc}")
        context = "System data temporarily unavailable."
        t_retrieved = time.monotonic()

    # Step 3: LLM generation
    from services.llm_service import answer_question_async
    answer = await answer_question_async(context, question, str(intent))

    t_done = time.monotonic()
    logger.info(
        f"RAG complete | intent={intent} "
        f"| db={((t_retrieved-t_classified)*1000):.0f}ms "
        f"| llm={((t_done-t_retrieved)*1000):.0f}ms "
        f"| total={((t_done-t_start)*1000):.0f}ms"
    )

    return answer