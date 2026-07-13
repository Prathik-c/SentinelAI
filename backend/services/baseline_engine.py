"""
SentinelAI — Behavioral Baseline Engine

Computes and caches the user's "normal" system behaviour from historical logs.
This is the intelligence foundation that the anomaly engine compares against.

Key responsibilities:
- Aggregate CPU/RAM/Disk statistics (mean, std_dev, percentiles).
- Build the known-process registry with frequency and resource usage.
- Build time-of-day usage patterns (by hour).
- Build day-of-week patterns.
- Cache results in-memory with a configurable TTL to avoid full table scans
  on every anomaly check request.
- Persist computed baselines to the BaselineSnapshot table for audit and
  comparison between weeks.
"""
from __future__ import annotations

import json
import statistics
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy.orm import Session

from config import (
    BASELINE_CACHE_TTL,
    KNOWN_PROCESS_THRESHOLD,
    MIN_BASELINE_SAMPLES,
)
from core.exceptions import BaselineNotReadyError


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class ProcessStats:
    """Aggregated statistics for a single process name."""
    name: str
    count: int                  # How many log snapshots contained this process
    avg_cpu: float              # Average CPU% when this process is running
    avg_ram: float              # Average RAM% when this process is running
    max_cpu: float              # Peak CPU% observed
    first_seen: str             # ISO timestamp of first appearance
    last_seen: str              # ISO timestamp of last appearance


@dataclass
class HourlyPattern:
    """Average resource usage for a given hour-of-day (0–23)."""
    hour: int
    avg_cpu: float
    avg_ram: float
    avg_idle: float
    sample_count: int


@dataclass
class BaselineStats:
    """
    Complete behavioural baseline for the system.
    All fields are serialisable to JSON for persistence.
    """
    sample_count: int = 0

    # CPU statistics
    cpu_mean: float = 0.0
    cpu_std: float  = 0.0
    cpu_min: float  = 0.0
    cpu_max: float  = 0.0
    cpu_p95: float  = 0.0

    # RAM statistics
    ram_mean: float = 0.0
    ram_std: float  = 0.0
    ram_min: float  = 0.0
    ram_max: float  = 0.0
    ram_p95: float  = 0.0

    # Disk statistics
    disk_mean: float = 0.0

    # Computed anomaly thresholds (used directly by anomaly_engine)
    cpu_threshold: float = 80.0
    ram_threshold: float = 90.0

    # Process registry: name → ProcessStats
    known_processes: Dict[str, ProcessStats] = field(default_factory=dict)

    # Patterns: hour (0-23) → HourlyPattern
    hourly_patterns: Dict[int, HourlyPattern] = field(default_factory=dict)

    # day_of_week (0=Mon … 6=Sun) → {avg_cpu, avg_ram}
    daily_patterns: Dict[int, Dict[str, float]] = field(default_factory=dict)

    # Process parent-child relationships
    process_graph: Dict[str, List[str]] = field(default_factory=dict)

    # Keyboard / Mouse activity statistics
    activity_patterns: Dict[str, Any] = field(default_factory=dict)

    # Known startup applications & services
    startup_patterns: str = ""

    # Computed at timestamp (ISO)
    computed_at: str = ""

    def is_process_known(self, name: str, min_threshold: float) -> bool:
        """
        Returns True if the process appeared in at least `min_threshold`
        fraction of all log samples.
        """
        if name not in self.known_processes:
            return False
        ps = self.known_processes[name]
        return (ps.count / self.sample_count) >= min_threshold

    def typical_cpu_for_hour(self, hour: int) -> Optional[float]:
        """Returns the average CPU for this hour-of-day, or None if no data."""
        hp = self.hourly_patterns.get(hour)
        return hp.avg_cpu if hp else None


# ── In-memory cache ───────────────────────────────────────────────────────────

_cache: Optional[BaselineStats] = None
_cache_timestamp: float = 0.0


def _cache_is_valid() -> bool:
    return _cache is not None and (time.monotonic() - _cache_timestamp) < BASELINE_CACHE_TTL


def invalidate_cache() -> None:
    """Force the next call to get_cached_baseline() to recompute."""
    global _cache, _cache_timestamp
    _cache = None
    _cache_timestamp = 0.0
    logger.debug("Baseline cache invalidated.")


# ── Core computation ──────────────────────────────────────────────────────────

def compute_baseline(db: Session) -> BaselineStats:
    """
    Reads all HealthLog rows and computes full behavioural baseline.

    Raises:
        BaselineNotReadyError: if fewer than MIN_BASELINE_SAMPLES rows exist.
    """
    from models.tables import HealthLog

    start = time.monotonic()

    # Load only the columns we need (avoid loading all TEXT blobs unnecessarily)
    logs = (
        db.query(HealthLog)
        .order_by(HealthLog.timestamp.asc())
        .all()
    )

    n = len(logs)
    if n < MIN_BASELINE_SAMPLES:
        raise BaselineNotReadyError(current=n, required=MIN_BASELINE_SAMPLES)

    # ── Aggregate metric lists ──────────────────────────────────────────────
    cpu_vals:  List[float] = []
    ram_vals:  List[float] = []
    disk_vals: List[float] = []

    # Process registry: name → {count, cpu_sum, ram_sum, max_cpu, first, last}
    proc_registry: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "count": 0, "cpu_sum": 0.0, "ram_sum": 0.0,
        "max_cpu": 0.0, "first_seen": None, "last_seen": None,
    })

    # Process parent-child mapping: parent_name -> set(child_names)
    process_graph_builder: Dict[str, set[str]] = defaultdict(set)

    # Activity/Input frequency aggregation
    idle_vals: List[float] = []
    event_vals: List[int] = []

    # Hourly buckets: hour → {cpu_sum, ram_sum, idle_sum, count}
    hourly: Dict[int, Dict[str, float]] = defaultdict(lambda: {
        "cpu_sum": 0.0, "ram_sum": 0.0, "idle_sum": 0.0, "count": 0,
    })

    # Daily buckets: day_of_week → {cpu_sum, ram_sum, count}
    daily: Dict[int, Dict[str, float]] = defaultdict(lambda: {
        "cpu_sum": 0.0, "ram_sum": 0.0, "count": 0,
    })

    for log in logs:
        ts: datetime = log.timestamp if isinstance(log.timestamp, datetime) \
                       else datetime.fromisoformat(str(log.timestamp))

        cpu_vals.append(log.cpu)
        ram_vals.append(log.ram)
        disk_vals.append(log.disk)

        if hasattr(log, "idle_seconds") and log.idle_seconds is not None:
            idle_vals.append(log.idle_seconds)
        if hasattr(log, "keyboard_mouse_events") and log.keyboard_mouse_events is not None:
            event_vals.append(log.keyboard_mouse_events)

        h = ts.hour
        hourly[h]["cpu_sum"]  += log.cpu
        hourly[h]["ram_sum"]  += log.ram
        hourly[h]["idle_sum"] += (log.idle_seconds or 0.0)
        hourly[h]["count"]    += 1

        dow = ts.weekday()  # 0=Monday
        daily[dow]["cpu_sum"] += log.cpu
        daily[dow]["ram_sum"] += log.ram
        daily[dow]["count"]   += 1

        if log.top_processes:
            try:
                procs = json.loads(log.top_processes)
            except (json.JSONDecodeError, ValueError):
                continue  # Skip malformed JSON — never crash baseline compute

            ts_iso = ts.isoformat()
            
            # Map PIDs to Names within this snapshot
            pid_to_name = {}
            for p in procs:
                p_name = (p.get("name") or "").strip()
                p_pid = p.get("pid")
                if p_name and p_pid:
                    pid_to_name[p_pid] = p_name

            for p in procs:
                name = (p.get("name") or "").strip()
                if not name:
                    continue
                cpu  = float(p.get("cpu", 0.0))
                ram  = float(p.get("ram", 0.0))
                reg  = proc_registry[name]
                reg["count"]   += 1
                reg["cpu_sum"] += cpu
                reg["ram_sum"] += ram
                reg["max_cpu"]  = max(reg["max_cpu"], cpu)
                if reg["first_seen"] is None:
                    reg["first_seen"] = ts_iso
                reg["last_seen"] = ts_iso

                # Map process to parent name if ppid is known and found in snapshot
                ppid = p.get("ppid")
                if ppid and ppid in pid_to_name:
                    parent_name = pid_to_name[ppid]
                    if parent_name != name:  # Avoid self-parent mapping
                        process_graph_builder[parent_name].add(name)

    # ── Statistical calculations ────────────────────────────────────────────
    def _pct(vals: List[float], p: float) -> float:
        """Return the p-th percentile of a sorted list."""
        if not vals:
            return 0.0
        s = sorted(vals)
        idx = max(0, int(len(s) * p / 100) - 1)
        return round(s[idx], 2)

    def _std(vals: List[float]) -> float:
        return round(statistics.stdev(vals), 2) if len(vals) > 1 else 0.0

    cpu_mean  = round(statistics.mean(cpu_vals),  2)
    cpu_std   = _std(cpu_vals)
    ram_mean  = round(statistics.mean(ram_vals),  2)
    ram_std   = _std(ram_vals)
    disk_mean = round(statistics.mean(disk_vals), 2)

    # Thresholds: mean + 3*std for CPU, mean + 2*std for RAM (capped)
    cpu_threshold = round(min(cpu_mean + 3 * cpu_std, 85.0), 1)
    ram_threshold = round(min(ram_mean + 2 * ram_std, 95.0), 1)

    # ── Build known-process registry ────────────────────────────────────────
    known_processes: Dict[str, ProcessStats] = {}
    for name, reg in proc_registry.items():
        cnt = reg["count"]
        known_processes[name] = ProcessStats(
            name       = name,
            count      = cnt,
            avg_cpu    = round(reg["cpu_sum"] / cnt, 2),
            avg_ram    = round(reg["ram_sum"] / cnt, 2),
            max_cpu    = round(reg["max_cpu"], 2),
            first_seen = reg["first_seen"] or "",
            last_seen  = reg["last_seen"] or "",
        )

    # ── Build hourly patterns ───────────────────────────────────────────────
    hourly_patterns: Dict[int, HourlyPattern] = {}
    for h, data in hourly.items():
        c = data["count"]
        hourly_patterns[h] = HourlyPattern(
            hour         = h,
            avg_cpu      = round(data["cpu_sum"]  / c, 2),
            avg_ram      = round(data["ram_sum"]  / c, 2),
            avg_idle     = round(data["idle_sum"] / c, 2),
            sample_count = c,
        )

    # ── Build daily patterns ────────────────────────────────────────────────
    daily_patterns: Dict[int, Dict[str, float]] = {}
    for dow, data in daily.items():
        c = data["count"]
        daily_patterns[dow] = {
            "avg_cpu": round(data["cpu_sum"] / c, 2),
            "avg_ram": round(data["ram_sum"] / c, 2),
        }

    # Convert sets to lists for json serialization
    process_graph = {k: list(v) for k, v in process_graph_builder.items()}

    # Compute activity averages
    avg_idle = round(statistics.mean(idle_vals), 2) if idle_vals else 0.0
    avg_events = round(statistics.mean(event_vals), 2) if event_vals else 0.0
    activity_patterns = {
        "avg_idle": avg_idle,
        "avg_events": avg_events
    }

    # Query startup patterns
    startup_patterns_list = []
    try:
        from services.analyzers.startup_analyzer import StartupAnalyzer
        sa = StartupAnalyzer()
        startup_patterns_list = list(set(sa.get_current_startup_items() + sa.get_current_services()))
    except Exception as exc:
        logger.warning(f"Could not retrieve startup patterns for baseline: {exc}")
    startup_patterns_str = json.dumps(startup_patterns_list)

    stats = BaselineStats(
        sample_count    = n,
        cpu_mean        = cpu_mean,
        cpu_std         = cpu_std,
        cpu_min         = round(min(cpu_vals),  2),
        cpu_max         = round(max(cpu_vals),  2),
        cpu_p95         = _pct(cpu_vals,  95),
        ram_mean        = ram_mean,
        ram_std         = ram_std,
        ram_min         = round(min(ram_vals),  2),
        ram_max         = round(max(ram_vals),  2),
        ram_p95         = _pct(ram_vals,  95),
        disk_mean       = disk_mean,
        cpu_threshold   = cpu_threshold,
        ram_threshold   = ram_threshold,
        known_processes = known_processes,
        hourly_patterns = hourly_patterns,
        daily_patterns  = daily_patterns,
        process_graph   = process_graph,
        activity_patterns = activity_patterns,
        startup_patterns = startup_patterns_str,
        computed_at     = datetime.utcnow().isoformat(),
    )

    elapsed = time.monotonic() - start
    logger.info(
        f"Baseline computed | samples={n} | cpu_mean={cpu_mean}% "
        f"ram_mean={ram_mean}% | elapsed={elapsed:.3f}s"
    )
    return stats


def get_cached_baseline(db: Session) -> BaselineStats:
    """
    Returns the cached baseline, computing it first if the cache is stale.
    This is the main entry point for all consumers.

    Raises:
        BaselineNotReadyError: propagated from compute_baseline if insufficient data.
    """
    global _cache, _cache_timestamp

    if _cache_is_valid():
        return _cache  # type: ignore[return-value]

    stats = compute_baseline(db)
    _cache = stats
    _cache_timestamp = time.monotonic()
    return stats


def persist_baseline(db: Session, stats: BaselineStats) -> None:
    """
    Saves the current baseline to the BaselineSnapshot table for historical
    audit. Only the most recent snapshot is used at runtime; old ones are
    retained for trend analysis and the weekly report.
    """
    from models.tables import BaselineSnapshot

    def _serialise_processes(procs: Dict[str, ProcessStats]) -> str:
        return json.dumps({k: asdict(v) for k, v in procs.items()})

    def _serialise_hourly(patterns: Dict[int, HourlyPattern]) -> str:
        return json.dumps({str(k): asdict(v) for k, v in patterns.items()})

    snapshot = BaselineSnapshot(
        sample_count    = stats.sample_count,
        cpu_mean        = stats.cpu_mean,
        cpu_std         = stats.cpu_std,
        cpu_p95         = stats.cpu_p95,
        ram_mean        = stats.ram_mean,
        ram_std         = stats.ram_std,
        ram_p95         = stats.ram_p95,
        disk_mean       = stats.disk_mean,
        known_processes = _serialise_processes(stats.known_processes),
        hourly_patterns = _serialise_hourly(stats.hourly_patterns),
        daily_patterns  = json.dumps(
            {str(k): v for k, v in stats.daily_patterns.items()}
        ),
        process_graph   = json.dumps(stats.process_graph),
        activity_patterns = json.dumps(stats.activity_patterns),
        startup_patterns = stats.startup_patterns,
    )
    try:
        db.add(snapshot)
        db.commit()
        logger.debug(f"Baseline snapshot persisted | id={snapshot.id}")
    except Exception as exc:
        db.rollback()
        logger.error(f"Failed to persist baseline snapshot: {exc}")
