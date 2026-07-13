"""
SentinelAI — PDF Report Generator (v2)

Extended to include:
  - Health Score (0–100) and Risk Score (0–100) prominently displayed.
  - Most CPU-intensive processes table.
  - First-seen processes section.
  - Peak usage hour annotation.
  - AI-generated narrative section.
  - Python-generated recommendations.
  - Accepts pre-computed stats dict from report_engine to avoid double queries.

All database queries are guarded against malformed JSON and empty datasets.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from loguru import logger
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy.orm import Session


# ── Colour palette ────────────────────────────────────────────────────────────
NAVY      = colors.HexColor("#0f172a")
BLUE      = colors.HexColor("#1e3a8a")
BLUE_MID  = colors.HexColor("#3b82f6")
SLATE_100 = colors.HexColor("#f1f5f9")
SLATE_200 = colors.HexColor("#e2e8f0")
SLATE_400 = colors.HexColor("#94a3b8")
SLATE_700 = colors.HexColor("#334155")
GREEN     = colors.HexColor("#16a34a")
AMBER     = colors.HexColor("#d97706")
RED       = colors.HexColor("#dc2626")
WHITE     = colors.white


def _score_colour(score: float, invert: bool = False) -> Any:
    """Returns a colour based on score (green = good, red = bad)."""
    if invert:  # Higher is worse (risk score)
        if score >= 70: return RED
        if score >= 40: return AMBER
        return GREEN
    else:       # Higher is better (health score)
        if score >= 70: return GREEN
        if score >= 40: return AMBER
        return RED


# ── Style factory ─────────────────────────────────────────────────────────────

def _make_styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "DocTitle", parent=base["Heading1"],
            fontName="Helvetica-Bold", fontSize=22,
            textColor=NAVY, spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "DocSubtitle", parent=base["Normal"],
            fontName="Helvetica", fontSize=9,
            textColor=SLATE_400, spaceAfter=20,
        ),
        "h2": ParagraphStyle(
            "SectionH2", parent=base["Heading2"],
            fontName="Helvetica-Bold", fontSize=13,
            textColor=NAVY, spaceBefore=18, spaceAfter=8,
        ),
        "body": ParagraphStyle(
            "Body", parent=base["Normal"],
            fontName="Helvetica", fontSize=9,
            textColor=SLATE_700, spaceAfter=6, leading=14,
        ),
        "th": ParagraphStyle(
            "TableHeader", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=9, textColor=WHITE,
        ),
        "td": ParagraphStyle(
            "TableCell", parent=base["Normal"],
            fontName="Helvetica", fontSize=8.5, textColor=SLATE_700,
        ),
        "score": ParagraphStyle(
            "Score", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=28, spaceAfter=2,
        ),
        "score_label": ParagraphStyle(
            "ScoreLabel", parent=base["Normal"],
            fontName="Helvetica", fontSize=9, textColor=SLATE_400,
        ),
        "narrative": ParagraphStyle(
            "Narrative", parent=base["Normal"],
            fontName="Helvetica", fontSize=9,
            textColor=SLATE_700, spaceAfter=6, leading=15,
        ),
    }


def _table_style(header_colour=BLUE) -> TableStyle:
    return TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), header_colour),
        ("ALIGN",         (0, 0), (-1, -1), "LEFT"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("GRID",          (0, 0), (-1, -1), 0.4, SLATE_200),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, SLATE_100]),
    ])


# ── Main generator ────────────────────────────────────────────────────────────

def generate_health_pdf(
    db: Session,
    output_path: str,
    days: int = 7,
    stats: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Generates a styled PDF system health report.

    Args:
        db:          SQLAlchemy session.
        output_path: Where to write the PDF.
        days:        Report period in days.
        stats:       Pre-computed stats dict (from report_engine).
                     If None, computes basic stats from the DB.

    Returns:
        The output_path on success.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    # ── Gather data ─────────────────────────────────────────────────────────
    if stats is None:
        stats = _compute_basic_stats(db, days)

    from models.tables import Incident
    cutoff   = datetime.utcnow() - timedelta(days=days)
    incidents = (
        db.query(Incident)
        .filter(Incident.timestamp >= cutoff)
        .order_by(Incident.timestamp.desc())
        .all()
    )

    # ── Build PDF ───────────────────────────────────────────────────────────
    doc = SimpleDocTemplate(
        output_path, pagesize=letter,
        leftMargin=40, rightMargin=40, topMargin=40, bottomMargin=40,
    )
    story = []
    S = _make_styles()

    # Title
    story.append(Paragraph("SentinelAI — System Health Report", S["title"]))
    story.append(Paragraph(
        f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  "
        f"Period: Last {days} Days  |  "
        f"Samples: {stats.get('total_samples', 0)}",
        S["subtitle"],
    ))

    # ── Scores ──────────────────────────────────────────────────────────────
    health_score = stats.get("health_score", 0)
    risk_score   = stats.get("risk_score",   0)
    h_col = _score_colour(health_score, invert=False)
    r_col = _score_colour(risk_score,   invert=True)

    score_data = [[
        Paragraph(f'<font color="#{_hex(h_col)}">{health_score}</font><font size="12">/100</font>', S["score"]),
        Paragraph(f'<font color="#{_hex(r_col)}">{risk_score}</font><font size="12">/100</font>', S["score"]),
    ], [
        Paragraph("Health Score", S["score_label"]),
        Paragraph("Risk Score",   S["score_label"]),
    ]]
    score_table = Table(score_data, colWidths=[255, 255])
    score_table.setStyle(TableStyle([
        ("ALIGN",  (0, 0), (-1, -1), "CENTER"),
        ("BOX",    (0, 0), (-1, -1), 0.5, SLATE_200),
        ("TOPPADDING",    (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("BACKGROUND", (0, 0), (-1, -1), SLATE_100),
    ]))
    story.append(score_table)
    story.append(Spacer(1, 16))

    # ── Resource Averages ───────────────────────────────────────────────────
    story.append(Paragraph("1. Resource Averages", S["h2"]))
    metrics_data = [
        [_th("Metric", S), _th("Average", S), _th("Peak", S)],
        [_td("CPU Utilisation", S), _td(f"{stats.get('avg_cpu', 0):.1f}%", S), _td(f"{stats.get('max_cpu', 0):.1f}%", S)],
        [_td("RAM Utilisation", S), _td(f"{stats.get('avg_ram', 0):.1f}%", S), _td(f"{stats.get('max_ram', 0):.1f}%", S)],
        [_td("Disk Usage (C:)", S), _td(f"{stats.get('avg_disk', 0):.1f}%", S), _td("—", S)],
    ]
    if stats.get("peak_hour") is not None:
        metrics_data.append([
            _td("Peak Activity Hour", S),
            _td(f"{stats['peak_hour']:02d}:00 — {stats.get('peak_hour_cpu', 0):.1f}% avg CPU", S),
            _td("", S),
        ])
    story.append(_build_table(metrics_data, [210, 150, 150], S))
    story.append(Spacer(1, 12))

    # ── Top CPU Processes ───────────────────────────────────────────────────
    story.append(Paragraph("2. Most CPU-Intensive Processes", S["h2"]))
    top_cpu = stats.get("top_processes_by_cpu", [])
    if top_cpu:
        proc_data = [[_th("Process", S), _th("Avg CPU", S), _th("Peak CPU", S)]]
        for p in top_cpu[:8]:
            proc_data.append([
                _td(p.get("name", "?"), S),
                _td(f"{p.get('avg_cpu', 0):.1f}%", S),
                _td(f"{p.get('max_cpu', 0):.1f}%", S),
            ])
        story.append(_build_table(proc_data, [270, 120, 120], S, header_colour=BLUE_MID))
    else:
        story.append(Paragraph("No process data available for this period.", S["body"]))
    story.append(Spacer(1, 12))

    # ── Most Frequent Processes ─────────────────────────────────────────────
    story.append(Paragraph("3. Most Frequently Active Processes", S["h2"]))
    top_freq = stats.get("top_processes_by_freq", [])
    if top_freq:
        freq_data = [[_th("Process", S), _th("Appearances", S)]]
        for p in top_freq[:8]:
            freq_data.append([_td(p["name"], S), _td(str(p["appearances"]), S)])
        story.append(_build_table(freq_data, [310, 200], S, header_colour=BLUE_MID))
    else:
        story.append(Paragraph("No process frequency data available.", S["body"]))
    story.append(Spacer(1, 12))

    # ── First-Seen Processes ────────────────────────────────────────────────
    first_seen = stats.get("first_seen_processes", [])
    if first_seen:
        story.append(Paragraph("4. New Processes (First Seen This Period)", S["h2"]))
        story.append(Paragraph(
            f"{len(first_seen)} process(es) appeared this week that were not seen in the previous period. "
            "Review these in the Alerts panel for any unfamiliar entries.",
            S["body"],
        ))
        fs_data = [[_th("Process Name", S)]]
        for name in first_seen[:15]:
            fs_data.append([_td(name, S)])
        story.append(_build_table(fs_data, [510], S, header_colour=AMBER))
        story.append(Spacer(1, 12))

    # ── Anomaly Summary ─────────────────────────────────────────────────────
    story.append(Paragraph("5. Security & Anomaly Log", S["h2"]))
    pending   = sum(1 for i in incidents if i.status == "pending")
    approved  = sum(1 for i in incidents if i.status == "approved")
    dismissed = sum(1 for i in incidents if i.status == "dismissed")
    story.append(Paragraph(
        f"<b>{len(incidents)}</b> anomalies detected | "
        f"<b>{approved}</b> acknowledged | "
        f"<b>{dismissed}</b> dismissed | "
        f"<b>{pending}</b> pending review",
        S["body"],
    ))
    story.append(Spacer(1, 6))

    if incidents:
        alert_data = [[
            _th("Timestamp", S), _th("Type", S),
            _th("Severity", S), _th("Description", S), _th("Status", S),
        ]]
        for inc in incidents[:10]:
            alert_data.append([
                _td(str(inc.timestamp)[:16],           S),
                _td((inc.type or "").replace("_", " "), S),
                _td((inc.severity or "").capitalize(),  S),
                _td(_truncate(inc.description or "", 60), S),
                _td((inc.status or "").capitalize(),    S),
            ])
        story.append(_build_table(
            alert_data, [95, 90, 65, 190, 70], S, header_colour=NAVY
        ))
    else:
        story.append(Paragraph(
            "✅ No anomalies detected in this period.", S["body"]
        ))
    story.append(Spacer(1, 12))

    # ── Recommendations ─────────────────────────────────────────────────────
    recs = stats.get("recommendations", [])
    if recs:
        story.append(Paragraph("6. Recommendations", S["h2"]))
        for rec in recs:
            story.append(Paragraph(f"• {rec}", S["body"]))
        story.append(Spacer(1, 12))

    # ── AI Narrative ────────────────────────────────────────────────────────
    narrative = stats.get("ai_narrative", "")
    if narrative:
        story.append(Paragraph("7. AI Executive Summary", S["h2"]))
        story.append(Paragraph(narrative, S["narrative"]))

    doc.build(story)
    logger.info(f"PDF generated: {output_path}")
    return output_path


# ── Helpers ───────────────────────────────────────────────────────────────────

def _th(text: str, S: dict) -> Paragraph:
    return Paragraph(text, S["th"])

def _td(text: str, S: dict) -> Paragraph:
    return Paragraph(str(text), S["td"])

def _truncate(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n-1] + "…"

def _hex(c) -> str:
    """Converts a reportlab colour to hex string (for inline markup)."""
    try:
        r, g, b = int(c.red * 255), int(c.green * 255), int(c.blue * 255)
        return f"{r:02X}{g:02X}{b:02X}"
    except Exception:
        return "334155"

def _build_table(data, col_widths, S, header_colour=None) -> Table:
    t = Table(data, colWidths=col_widths)
    t.setStyle(_table_style(header_colour or BLUE))
    return t

def _compute_basic_stats(db: Session, days: int) -> Dict[str, Any]:
    """Fallback stats computation when report_engine stats are not provided."""
    from models.tables import HealthLog
    from services.report_engine import compute_weekly_stats
    try:
        return compute_weekly_stats(db, days=days)
    except Exception as exc:
        logger.error(f"Basic stats computation failed: {exc}")
        cutoff = datetime.utcnow() - timedelta(days=days)
        logs   = db.query(HealthLog).filter(HealthLog.timestamp >= cutoff).all()
        n      = len(logs)
        if n == 0:
            return {"total_samples": 0, "avg_cpu": 0, "avg_ram": 0,
                    "avg_disk": 0, "max_cpu": 0, "max_ram": 0,
                    "health_score": 0, "risk_score": 0}
        cpu  = [l.cpu for l in logs]
        ram  = [l.ram for l in logs]
        disk = [l.disk for l in logs]
        return {
            "total_samples": n,
            "avg_cpu":  round(sum(cpu)  / n, 1),
            "max_cpu":  round(max(cpu),      1),
            "avg_ram":  round(sum(ram)  / n, 1),
            "max_ram":  round(max(ram),      1),
            "avg_disk": round(sum(disk) / n, 1),
            "health_score": 70, "risk_score": 0,
        }
