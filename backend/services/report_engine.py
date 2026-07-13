"""
SentinelAI — Weekly Report Engine

Computes all statistics needed for the weekly system health report using pure
Python — no LLM involved until the final narrative generation step.

Computed stats include:
  - Average CPU/RAM/Disk
  - Peak usage hours (by hour-of-day)
  - Most frequent processes
  - Most CPU-intensive processes
  - First-seen processes (appeared for the first time this week)
  - Health score (0–100, deterministic formula)
  - Risk score (0–100, based on incident severity)
  - Behaviour change indicators vs previous week
  - Python-generated recommendations

The stats dict is then:
  a) Used to generate the PDF and HTML reports
  b) Passed to the LLM for narrative generation
  c) Persisted to the WeeklyReport table
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy.orm import Session


# ── Stats Data Structure ──────────────────────────────────────────────────────

def _empty_stats() -> Dict[str, Any]:
    return {
        "period_days":          7,
        "generated_at":         datetime.utcnow().isoformat(),
        "total_samples":        0,
        "avg_cpu":              0.0,
        "max_cpu":              0.0,
        "avg_ram":              0.0,
        "max_ram":              0.0,
        "avg_disk":             0.0,
        "peak_hour":            None,
        "peak_hour_cpu":        0.0,
        "idle_hours":           [],
        "most_frequent_process": "",
        "top_processes_by_freq": [],
        "top_processes_by_cpu":  [],
        "first_seen_processes":  [],
        "total_anomalies":       0,
        "anomalies_by_severity": {},
        "unresolved_anomalies":  0,
        "health_score":          100,
        "risk_score":            0,
        "recommendations":       [],
        "behaviour_changes":     [],
    }


# ── Core Statistics ───────────────────────────────────────────────────────────

def compute_weekly_stats(db: Session, days: int = 7) -> Dict[str, Any]:
    """
    Queries the last `days` days of health logs and incidents,
    then computes the full statistics dict for the report.
    """
    from models.tables import HealthLog, Incident

    stats = _empty_stats()
    stats["period_days"] = days
    cutoff = datetime.utcnow() - timedelta(days=days)
    prev_cutoff = cutoff - timedelta(days=days)  # For trend comparison

    # ── Health logs ─────────────────────────────────────────────────────────
    logs = (
        db.query(HealthLog)
        .filter(HealthLog.timestamp >= cutoff)
        .order_by(HealthLog.timestamp.asc())
        .all()
    )

    n = len(logs)
    stats["total_samples"] = n

    if n == 0:
        logger.warning("No health logs found for the report period.")
        return stats

    cpu_vals  = [l.cpu for l in logs]
    ram_vals  = [l.ram for l in logs]
    disk_vals = [l.disk for l in logs]

    stats["avg_cpu"]  = round(sum(cpu_vals)  / n, 1)
    stats["max_cpu"]  = round(max(cpu_vals),      1)
    stats["avg_ram"]  = round(sum(ram_vals)  / n, 1)
    stats["max_ram"]  = round(max(ram_vals),      1)
    stats["avg_disk"] = round(sum(disk_vals) / n, 1)

    # ── Hourly CPU patterns ─────────────────────────────────────────────────
    hourly_cpu: Dict[int, List[float]] = defaultdict(list)
    hourly_idle: Dict[int, float] = defaultdict(float)

    for log in logs:
        ts = log.timestamp if isinstance(log.timestamp, datetime) \
             else datetime.fromisoformat(str(log.timestamp))
        h = ts.hour
        hourly_cpu[h].append(log.cpu)
        if log.idle_seconds:
            hourly_idle[h] += log.idle_seconds

    if hourly_cpu:
        hourly_avgs = {
            h: sum(cpus) / len(cpus)
            for h, cpus in hourly_cpu.items()
        }
        peak_hour     = max(hourly_avgs, key=hourly_avgs.get)
        stats["peak_hour"]     = peak_hour
        stats["peak_hour_cpu"] = round(hourly_avgs[peak_hour], 1)

        # Idle hours: hours where avg CPU < 5% and avg idle > 300s
        idle_hours = [
            h for h, avg in hourly_avgs.items()
            if avg < 5.0 and hourly_idle.get(h, 0) / max(len(hourly_cpu[h]), 1) > 300
        ]
        stats["idle_hours"] = sorted(idle_hours)

    # ── Process frequency & CPU analysis ────────────────────────────────────
    proc_counts: Dict[str, int]   = defaultdict(int)
    proc_cpu:    Dict[str, List[float]] = defaultdict(list)
    prev_procs:  set[str]         = set()

    # Get all processes from the previous period for "first seen" detection
    prev_logs = (
        db.query(HealthLog)
        .filter(HealthLog.timestamp >= prev_cutoff, HealthLog.timestamp < cutoff)
        .all()
    )
    for plog in prev_logs:
        if plog.top_processes:
            try:
                for p in json.loads(plog.top_processes):
                    prev_procs.add(p.get("name", ""))
            except json.JSONDecodeError:
                pass

    current_procs: set[str] = set()
    for log in logs:
        if not log.top_processes:
            continue
        try:
            procs = json.loads(log.top_processes)
        except json.JSONDecodeError:
            continue
        for p in procs:
            name = (p.get("name") or "").strip()
            if not name:
                continue
            cpu  = p.get("cpu", 0.0)
            proc_counts[name]  += 1
            proc_cpu[name].append(cpu)
            current_procs.add(name)

    # Most frequent processes
    top_by_freq = sorted(proc_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    stats["top_processes_by_freq"] = [
        {"name": name, "appearances": count}
        for name, count in top_by_freq
    ]
    stats["most_frequent_process"] = top_by_freq[0][0] if top_by_freq else ""

    # Most CPU-intensive processes (by avg CPU when active)
    top_by_cpu = sorted(
        [
            {
                "name": name,
                "avg_cpu": round(sum(cpus) / len(cpus), 1),
                "max_cpu": round(max(cpus), 1),
            }
            for name, cpus in proc_cpu.items()
            if cpus
        ],
        key=lambda x: x["avg_cpu"],
        reverse=True,
    )[:10]
    stats["top_processes_by_cpu"] = top_by_cpu

    # First-seen processes (appeared this week, never seen last week)
    first_seen = sorted(current_procs - prev_procs)
    stats["first_seen_processes"] = first_seen[:20]  # Cap at 20

    # ── Incidents / anomalies ────────────────────────────────────────────────
    from models.tables import Incident

    incidents = (
        db.query(Incident)
        .filter(Incident.timestamp >= cutoff)
        .all()
    )

    stats["total_anomalies"] = len(incidents)
    stats["unresolved_anomalies"] = sum(
        1 for i in incidents if i.status == "pending"
    )

    sev_counts: Dict[str, int] = defaultdict(int)
    for inc in incidents:
        sev_counts[inc.severity] += 1
    stats["anomalies_by_severity"] = dict(sev_counts)

    # ── Health Score (0–100) ─────────────────────────────────────────────────
    stats["health_score"] = compute_health_score(stats)

    # ── Risk Score (0–100) ───────────────────────────────────────────────────
    stats["risk_score"] = compute_risk_score(incidents)

    # ── Recommendations ──────────────────────────────────────────────────────
    stats["recommendations"] = generate_recommendations(stats, incidents)

    logger.info(
        f"Weekly stats computed | period={days}d | samples={n} "
        f"| anomalies={len(incidents)} | health={stats['health_score']} "
        f"| risk={stats['risk_score']}"
    )

    return stats


def compute_health_score(stats: Dict[str, Any]) -> int:
    """
    Deterministic formula for health score (0–100, higher is better).

    Deductions:
      - High avg CPU (> 70%): -20
      - High avg RAM (> 85%): -20
      - High disk (> 90%):    -15
      - Many anomalies:       -10 per 5 anomalies (max -30)
      - Unresolved anomalies: -5 per unresolved (max -15)
    """
    score = 100

    if stats["avg_cpu"] > 70:
        score -= 20
    elif stats["avg_cpu"] > 50:
        score -= 10

    if stats["avg_ram"] > 85:
        score -= 20
    elif stats["avg_ram"] > 70:
        score -= 10

    if stats["avg_disk"] > 90:
        score -= 15
    elif stats["avg_disk"] > 80:
        score -= 5

    total_anomalies   = stats.get("total_anomalies", 0)
    unresolved        = stats.get("unresolved_anomalies", 0)
    score -= min((total_anomalies // 5) * 10, 30)
    score -= min(unresolved * 5, 15)

    return max(0, min(100, score))


def compute_risk_score(incidents: list) -> int:
    """
    Deterministic formula for risk score (0–100, higher is riskier).

    Points per incident by severity:
      critical → 25
      high     → 15
      medium   → 8
      low      → 3
    Total capped at 100.
    """
    severity_weights = {"critical": 25, "high": 15, "medium": 8, "low": 3}
    total = sum(severity_weights.get(i.severity, 5) for i in incidents)
    return min(total, 100)


def generate_recommendations(
    stats: Dict[str, Any],
    incidents: list,
) -> List[str]:
    """
    Rule-based recommendation generator.
    All logic is deterministic Python — no LLM required.
    """
    recs: List[str] = []

    if stats["avg_cpu"] > 60:
        recs.append(
            f"Average CPU was {stats['avg_cpu']:.1f}% this week. "
            "Consider closing unused background applications."
        )

    if stats["avg_ram"] > 80:
        recs.append(
            f"Average RAM usage was {stats['avg_ram']:.1f}%. "
            "Consider upgrading RAM or closing memory-heavy applications."
        )

    if stats["avg_disk"] > 85:
        recs.append(
            f"Disk usage is at {stats['avg_disk']:.1f}%. "
            "Run Disk Cleanup or expand storage to prevent performance degradation."
        )

    if stats.get("first_seen_processes"):
        count = len(stats["first_seen_processes"])
        recs.append(
            f"{count} new process(es) appeared this week that were never seen before. "
            "Review them in the Alerts panel."
        )

    critical_count = stats["anomalies_by_severity"].get("critical", 0)
    if critical_count > 0:
        recs.append(
            f"{critical_count} critical anomalies were detected this week. "
            "Review and acknowledge them in the Alerts panel."
        )

    if stats.get("unresolved_anomalies", 0) > 5:
        recs.append(
            f"{stats['unresolved_anomalies']} alerts are still unresolved. "
            "Review and dismiss or acknowledge them to keep the audit trail clean."
        )

    if not recs:
        recs.append(
            "System behaviour was within normal parameters this week. "
            "No immediate action required."
        )

    return recs


# ── Report Generation Orchestrator ───────────────────────────────────────────

async def generate_weekly_report(db: Session, days: int = 7) -> Dict[str, Any]:
    """
    Full report generation pipeline:
    1. Compute weekly stats (Python)
    2. Generate PDF + HTML (Python, reportlab/jinja2)
    3. Generate AI narrative (LLM, async)
    4. Persist to WeeklyReport table

    Returns the WeeklyReport metadata dict.
    """
    from config import REPORTS_DIR
    import os

    start = time.monotonic()
    os.makedirs(REPORTS_DIR, exist_ok=True)

    # Step 1: Compute stats
    stats = compute_weekly_stats(db, days=days)

    # Step 2: Generate PDF
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_filename  = f"sentinel_weekly_{timestamp_str}.pdf"
    html_filename = f"sentinel_weekly_{timestamp_str}.html"
    pdf_path      = os.path.join(REPORTS_DIR, pdf_filename)
    html_path     = os.path.join(REPORTS_DIR, html_filename)

    try:
        from utils.pdf_generator import generate_health_pdf
        generate_health_pdf(db, pdf_path, days=days, stats=stats)
        logger.info(f"Weekly PDF generated: {pdf_path}")
    except Exception as exc:
        logger.error(f"PDF generation failed: {exc}")
        pdf_path = None

    # Step 3: Generate AI narrative (async, with fallback)
    try:
        from services.llm_service import generate_weekly_narrative_async
        narrative = await generate_weekly_narrative_async(stats)
    except Exception as exc:
        logger.error(f"Weekly narrative LLM failed: {exc}")
        narrative = (
            "AI narrative generation is unavailable. "
            "All quantitative data above is accurate."
        )

    stats["ai_narrative"] = narrative

    # Generate simple HTML report
    try:
        _generate_html_report(stats, html_path)
        logger.info(f"Weekly HTML generated: {html_path}")
    except Exception as exc:
        logger.error(f"HTML generation failed: {exc}")
        html_path = None

    # Step 4: Persist to WeeklyReport table
    try:
        from models.tables import WeeklyReport

        report = WeeklyReport(
            period_days  = days,
            health_score = stats["health_score"],
            risk_score   = stats["risk_score"],
            pdf_path     = pdf_path,
            html_path    = html_path,
            summary_json = json.dumps(stats),
            ai_narrative = narrative,
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        logger.info(f"Weekly report persisted | id={report.id}")
    except Exception as exc:
        db.rollback()
        logger.error(f"Failed to persist weekly report: {exc}")
        report = None

    elapsed = time.monotonic() - start
    logger.info(f"Weekly report complete | elapsed={elapsed:.2f}s")

    return {
        "stats":        stats,
        "pdf_path":     pdf_path,
        "html_path":    html_path,
        "report_id":    report.id if report else None,
        "health_score": stats["health_score"],
        "risk_score":   stats["risk_score"],
    }


def _generate_html_report(stats: Dict[str, Any], html_path: str) -> None:
    """Generates a simple HTML version of the weekly report."""
    recs_html = "".join(
        f"<li>{r}</li>" for r in stats.get("recommendations", [])
    )
    first_seen_html = "".join(
        f"<li><code>{p}</code></li>"
        for p in stats.get("first_seen_processes", [])[:10]
    )
    top_cpu_html = "".join(
        f"<tr><td>{p['name']}</td><td>{p['avg_cpu']}%</td><td>{p['max_cpu']}%</td></tr>"
        for p in stats.get("top_processes_by_cpu", [])[:10]
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>SentinelAI Weekly Report</title>
  <style>
    body {{ font-family: 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 2rem; }}
    h1 {{ color: #60a5fa; }} h2 {{ color: #94a3b8; border-bottom: 1px solid #334155; padding-bottom: .5rem; }}
    .card {{ background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 1.5rem; margin: 1rem 0; }}
    .score {{ font-size: 2rem; font-weight: 900; }}
    .green {{ color: #34d399; }} .red {{ color: #f87171; }} .yellow {{ color: #fbbf24; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: .5rem .75rem; text-align: left; border-bottom: 1px solid #334155; }}
    th {{ color: #60a5fa; }} li {{ margin: .4rem 0; }} code {{ color: #a78bfa; }}
  </style>
</head>
<body>
  <h1>🛡️ SentinelAI Weekly Report</h1>
  <p>Generated: {stats['generated_at']} UTC | Period: Last {stats['period_days']} days</p>

  <div class="card">
    <h2>📊 Scores</h2>
    <p>Health Score: <span class="score {'green' if stats['health_score'] >= 70 else 'yellow' if stats['health_score'] >= 40 else 'red'}">{stats['health_score']}/100</span></p>
    <p>Risk Score: <span class="score {'green' if stats['risk_score'] <= 30 else 'yellow' if stats['risk_score'] <= 60 else 'red'}">{stats['risk_score']}/100</span></p>
  </div>

  <div class="card">
    <h2>💻 Resource Averages</h2>
    <table>
      <tr><th>Metric</th><th>Average</th><th>Peak</th></tr>
      <tr><td>CPU</td><td>{stats['avg_cpu']:.1f}%</td><td>{stats['max_cpu']:.1f}%</td></tr>
      <tr><td>RAM</td><td>{stats['avg_ram']:.1f}%</td><td>{stats['max_ram']:.1f}%</td></tr>
      <tr><td>Disk</td><td>{stats['avg_disk']:.1f}%</td><td>—</td></tr>
    </table>
  </div>

  <div class="card">
    <h2>⚡ Top CPU Processes</h2>
    <table>
      <tr><th>Process</th><th>Avg CPU</th><th>Peak CPU</th></tr>
      {top_cpu_html}
    </table>
  </div>

  <div class="card">
    <h2>🆕 First-Seen Processes This Week</h2>
    {'<ul>' + first_seen_html + '</ul>' if first_seen_html else '<p>None — all processes were previously known.</p>'}
  </div>

  <div class="card">
    <h2>🚨 Anomaly Summary</h2>
    <p>Total: {stats['total_anomalies']} | Unresolved: {stats['unresolved_anomalies']}</p>
    <p>By severity: {json.dumps(stats.get('anomalies_by_severity', {}))}</p>
  </div>

  <div class="card">
    <h2>✅ Recommendations</h2>
    <ul>{recs_html}</ul>
  </div>

  <div class="card">
    <h2>🤖 AI Narrative</h2>
    <p style="white-space: pre-wrap; line-height: 1.7;">{stats.get('ai_narrative', 'Not available.')}</p>
  </div>
</body>
</html>"""

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
