"""
SentinelAI — SQLAlchemy ORM Models (Database Tables)

Design notes:
- All timestamps stored as UTC via server_default=func.now().
- JSON blobs (top_processes, reasons) stored as Text; parse with json.loads().
- Indexes placed on every column used in WHERE / ORDER BY clauses.
- New tables: BaselineSnapshot (cached baselines), WeeklyReport (auto-reports).
- Incident extended with risk_score, reasons, process_name for richer data.
"""
from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.sql import func

from database import Base


# ── HealthLog ──────────────────────────────────────────────────────────────────

class HealthLog(Base):
    """One snapshot of system resource usage, logged every minute."""

    __tablename__ = "health_logs"

    id            = Column(Integer, primary_key=True, index=True)
    timestamp     = Column(DateTime, server_default=func.now(), nullable=False)
    cpu           = Column(Float, nullable=False)
    ram           = Column(Float, nullable=False)
    disk          = Column(Float, nullable=False)
    gpu           = Column(Float, nullable=True)  # New: GPU utilization
    top_processes = Column(Text, nullable=True)   # JSON: [{name, cpu, ram, pid, ppid}]
    idle_seconds  = Column(Float, nullable=True)
    foreground_app= Column(String(255), nullable=True) # New: Active window
    keyboard_mouse_events = Column(Integer, nullable=True) # New: Input frequency

    __table_args__ = (
        # Most queries filter/order by timestamp
        Index("ix_health_logs_timestamp", "timestamp"),
    )


# ── Incident ───────────────────────────────────────────────────────────────────

class Incident(Base):
    """
    A detected behavioural anomaly or security event.
    Python generates the structured fields; the LLM fills `report` asynchronously.
    """

    __tablename__ = "incidents"

    id            = Column(Integer, primary_key=True, index=True)
    timestamp     = Column(DateTime, server_default=func.now(), nullable=False)

    # Anomaly classification
    type          = Column(String(64), default="anomaly",  nullable=False)
    analyzer_name = Column(String(64), nullable=True)      # Which analyzer caught this
    severity      = Column(String(16), default="medium",   nullable=False)
    status        = Column(String(16), default="pending",  nullable=False)

    # Human-readable one-liner (Python-generated, not LLM)
    description   = Column(Text, nullable=True)

    # Extended structured data for the new Incident Engine
    process_name  = Column(String(255), nullable=True)
    risk_score    = Column(Float, nullable=True)           # 0–100
    reasons       = Column(Text, nullable=True)            # JSON: ["reason1", ...]
    snapshot      = Column(Text, nullable=True)            # JSON: baseline context

    # LLM-generated explanation (filled asynchronously after incident is saved)
    report        = Column(Text, nullable=True)

    # Audit fields
    approved_at   = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_incidents_timestamp",      "timestamp"),
        Index("ix_incidents_status",         "status"),
        Index("ix_incidents_type_status",    "type", "status"),
        Index("ix_incidents_timestamp_type", "timestamp", "type"),
    )


# ── ChatHistory ────────────────────────────────────────────────────────────────

class ChatHistory(Base):
    """Persisted Q&A pairs from the RAG chatbot."""

    __tablename__ = "chat_history"

    id        = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, server_default=func.now(), nullable=False)
    question  = Column(Text, nullable=False)
    answer    = Column(Text, nullable=False)
    intent    = Column(String(64), nullable=True)  # Classified intent for analytics

    __table_args__ = (
        Index("ix_chat_history_timestamp", "timestamp"),
    )


# ── BaselineSnapshot ──────────────────────────────────────────────────────────

class BaselineSnapshot(Base):
    """
    Cached, pre-computed baseline statistics.
    Updated by the hourly background task so anomaly checks are instant
    (no full table scan on every request).
    """

    __tablename__ = "baseline_snapshots"

    id               = Column(Integer, primary_key=True, index=True)
    computed_at      = Column(DateTime, server_default=func.now(), nullable=False)

    # Aggregate stats (all as floats)
    sample_count     = Column(Integer,  nullable=False, default=0)
    cpu_mean         = Column(Float,    nullable=False, default=0.0)
    cpu_std          = Column(Float,    nullable=False, default=0.0)
    cpu_p95          = Column(Float,    nullable=False, default=0.0)
    ram_mean         = Column(Float,    nullable=False, default=0.0)
    ram_std          = Column(Float,    nullable=False, default=0.0)
    ram_p95          = Column(Float,    nullable=False, default=0.0)
    disk_mean        = Column(Float,    nullable=False, default=0.0)
    gpu_mean         = Column(Float,    nullable=True, default=0.0)

    # JSON: {process_name: {count, avg_cpu, avg_ram, first_seen, last_seen}}
    known_processes  = Column(Text, nullable=True)
    # JSON: {parent: [children...]} for process relationships
    process_graph    = Column(Text, nullable=True)

    # JSON: {hour_of_day: {avg_cpu, avg_ram, avg_idle}} for time-of-day patterns
    hourly_patterns  = Column(Text, nullable=True)

    # JSON: {day_of_week: {avg_cpu, avg_ram}} for weekly patterns
    daily_patterns   = Column(Text, nullable=True)
    
    # JSON: {avg_idle_time, app_switch_frequency}
    activity_patterns= Column(Text, nullable=True)
    
    # JSON: [list of known startup services/apps]
    startup_patterns = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_baseline_snapshots_computed_at", "computed_at"),
    )


# ── WeeklyReport ──────────────────────────────────────────────────────────────

class WeeklyReport(Base):
    """Metadata for auto-generated weekly system health reports."""

    __tablename__ = "weekly_reports"

    id              = Column(Integer, primary_key=True, index=True)
    generated_at    = Column(DateTime, server_default=func.now(), nullable=False)
    period_days     = Column(Integer, nullable=False, default=7)

    # Computed scores (0–100)
    health_score    = Column(Float, nullable=True)
    risk_score      = Column(Float, nullable=True)

    # File paths on disk
    pdf_path        = Column(String(512), nullable=True)
    html_path       = Column(String(512), nullable=True)

    # JSON blob of the full stats dict used to generate the report
    summary_json    = Column(Text, nullable=True)

    # LLM-generated narrative paragraph
    ai_narrative    = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_weekly_reports_generated_at", "generated_at"),
    )