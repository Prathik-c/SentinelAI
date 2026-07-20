"""
SentinelAI — Logging Configuration

Uses loguru for structured, rotating log files with separate handlers for:
  - Console output (colourised, human-readable)
  - File output (JSON-structured, rotating, 7-day retention)

Call ``setup_logging()`` once at application startup before anything else.
"""
from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from config import LOG_LEVEL, LOGS_DIR


def setup_logging() -> None:
    """
    Configure loguru with rotating file and console sinks.
    Safe to call multiple times (removes existing handlers first).
    """
    # Remove default loguru handler
    logger.remove()

    # ── Console sink ───────────────────────────────────────────────────────
    logger.add(
        sys.stderr,
        level=LOG_LEVEL,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

    # ── Rotating file sink (Main / Application) ────────────────────────────
    log_dir = Path(LOGS_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)

    base_format = (
        "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | "
        "{name}:{function}:{line} | {message}"
    )

    def _add_sink(filename: str, filter_fn=None, level=LOG_LEVEL):
        logger.add(
            log_dir / filename,
            level=level,
            format=base_format,
            rotation="10 MB",
            retention="7 days",
            compression="gz",
            backtrace=True,
            diagnose=True,
            enqueue=True,
            filter=filter_fn
        )

    # 1. Main application log (everything)
    _add_sink("application.log")

    # 2. Errors only
    _add_sink("sentinelai_errors.log", level="ERROR")

    # 3. LLM / Ollama
    _add_sink("llm.log", filter_fn=lambda r: any(x in r["name"].lower() for x in ["ollama", "llm", "rag", "intent"]))

    # 4. Behavior Engine
    _add_sink("behavior.log", filter_fn=lambda r: any(x in r["name"].lower() for x in ["anomaly", "baseline", "analyzer", "incident", "activity", "scheduler"]))

    # 5. Database
    _add_sink("database.log", filter_fn=lambda r: any(x in r["name"].lower() for x in ["database", "schema", "migrator"]))

    # 6. Backend / API
    _add_sink("backend.log", filter_fn=lambda r: any(x in r["name"].lower() for x in ["router", "uvicorn", "fastapi", "main"]))

    # 7. Startup / CLI
    _add_sink("startup.log", filter_fn=lambda r: any(x in r["name"].lower() for x in ["cli", "startup", "doctor", "config"]))

    logger.info(
        f"Logging initialised | level={LOG_LEVEL} | log_dir={log_dir.resolve()}"
    )
