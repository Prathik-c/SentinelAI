"""
SentinelAI — Reports Router

Wraps blocking PDF generation in a thread pool so it never blocks the event loop.
Adds weekly report endpoints and proper error handling.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from loguru import logger
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import REPORTS_DIR
from database import get_db

router = APIRouter(prefix="/reports", tags=["Reports"])


class GenerateReportRequest(BaseModel):
    days: int = 7


class EmailReportRequest(BaseModel):
    days:          int = 7
    smtp_host:     str
    smtp_port:     int = 587
    smtp_user:     str
    smtp_password: str
    recipient:     str


@router.post("/generate")
async def generate_report(
    request: GenerateReportRequest,
    db:      Session = Depends(get_db),
):
    """
    Generates a PDF health report on-demand and returns it as a download.
    PDF generation runs in a thread pool (blocking I/O, never blocks event loop).
    """
    os.makedirs(REPORTS_DIR, exist_ok=True)
    timestamp    = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_filename = f"sentinel_health_report_{timestamp}.pdf"
    pdf_path     = os.path.join(REPORTS_DIR, pdf_filename)

    try:
        from utils.pdf_generator import generate_health_pdf
        await run_in_threadpool(
            generate_health_pdf, db, pdf_path, request.days
        )
    except Exception as exc:
        logger.error(f"POST /reports/generate error: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate report: {str(exc)}"
        )

    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=500, detail="PDF file was not created.")

    return FileResponse(
        path       = pdf_path,
        filename   = pdf_filename,
        media_type = "application/pdf",
    )


@router.post("/generate-weekly")
async def generate_weekly_report_endpoint(db: Session = Depends(get_db)):
    """
    Triggers on-demand weekly report generation (PDF + HTML + AI narrative).
    This is the same pipeline used by the automatic weekly scheduler.
    """
    try:
        from services.report_engine import generate_weekly_report
        result = await generate_weekly_report(db, days=7)
        return {
            "status":       "success",
            "report_id":    result.get("report_id"),
            "health_score": result.get("health_score"),
            "risk_score":   result.get("risk_score"),
            "pdf_path":     result.get("pdf_path"),
            "html_path":    result.get("html_path"),
        }
    except Exception as exc:
        logger.error(f"POST /reports/generate-weekly error: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Weekly report generation failed: {str(exc)}"
        )


@router.get("/weekly/latest")
def get_latest_weekly_report(db: Session = Depends(get_db)):
    """Returns metadata for the most recent auto-generated weekly report."""
    from models.tables import WeeklyReport
    import json

    try:
        report = (
            db.query(WeeklyReport)
            .order_by(WeeklyReport.generated_at.desc())
            .first()
        )
        if not report:
            return {"status": "no_report", "message": "No weekly reports generated yet."}

        stats = {}
        if report.summary_json:
            try:
                stats = json.loads(report.summary_json)
            except json.JSONDecodeError:
                pass

        return {
            "id":           report.id,
            "generated_at": str(report.generated_at),
            "period_days":  report.period_days,
            "health_score": report.health_score,
            "risk_score":   report.risk_score,
            "pdf_path":     report.pdf_path,
            "html_path":    report.html_path,
            "ai_narrative": report.ai_narrative,
            "stats": {
                "avg_cpu":              stats.get("avg_cpu"),
                "avg_ram":              stats.get("avg_ram"),
                "total_anomalies":      stats.get("total_anomalies"),
                "recommendations":      stats.get("recommendations", []),
                "first_seen_processes": stats.get("first_seen_processes", []),
            },
        }
    except Exception as exc:
        logger.error(f"GET /reports/weekly/latest error: {exc}")
        raise HTTPException(status_code=500, detail="Failed to retrieve latest report.")


@router.get("/list")
def list_reports(
    db:    Session = Depends(get_db),
    limit: int = Query(default=10, ge=1, le=50),
):
    """Lists all stored weekly reports with basic metadata."""
    from models.tables import WeeklyReport

    try:
        reports = (
            db.query(WeeklyReport)
            .order_by(WeeklyReport.generated_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id":           r.id,
                "generated_at": str(r.generated_at),
                "period_days":  r.period_days,
                "health_score": r.health_score,
                "risk_score":   r.risk_score,
                "has_pdf":      bool(r.pdf_path),
                "has_html":     bool(r.html_path),
            }
            for r in reports
        ]
    except Exception as exc:
        logger.error(f"GET /reports/list error: {exc}")
        raise HTTPException(status_code=500, detail="Failed to retrieve report list.")


@router.post("/send-email")
async def send_email_report(
    request: EmailReportRequest,
    db:      Session = Depends(get_db),
):
    """Generates a report and sends it via SMTP."""
    import smtplib
    from email import encoders
    from email.mime.base import MIMEBase
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    os.makedirs(REPORTS_DIR, exist_ok=True)
    pdf_path = os.path.join(REPORTS_DIR, "sentinel_health_report_email.pdf")

    # Generate PDF in thread pool
    try:
        from utils.pdf_generator import generate_health_pdf
        await run_in_threadpool(
            generate_health_pdf, db, pdf_path, request.days
        )
    except Exception as exc:
        logger.error(f"Email report PDF generation failed: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate PDF: {str(exc)}"
        )

    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=500, detail="PDF was not created.")

    # Send email
    try:
        msg = MIMEMultipart()
        msg["From"]    = request.smtp_user
        msg["To"]      = request.recipient
        msg["Subject"] = (
            f"SentinelAI System Health Report — "
            f"{datetime.now().strftime('%Y-%m-%d')}"
        )

        body = (
            f"Please find attached the SentinelAI System Health Report "
            f"for the past {request.days} days.\n\n"
            "This report was generated locally on your machine.\n\n"
            "— SentinelAI Security Daemon"
        )
        msg.attach(MIMEText(body, "plain"))

        with open(pdf_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                "attachment; filename=sentinel_health_report.pdf",
            )
            msg.attach(part)

        server = smtplib.SMTP(request.smtp_host, request.smtp_port)
        server.starttls()
        server.login(request.smtp_user, request.smtp_password)
        server.sendmail(request.smtp_user, request.recipient, msg.as_string())
        server.quit()

        return {
            "status":  "success",
            "message": f"Report emailed to {request.recipient}",
        }

    except Exception as exc:
        logger.error(f"Email send failed: {exc}")
        raise HTTPException(
            status_code=500,
            detail=(
                f"Failed to send email. Check SMTP settings. Error: {str(exc)}"
            ),
        )
