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

    # ── Rotating file sink ─────────────────────────────────────────────────
    log_dir = Path(LOGS_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.add(
        log_dir / "sentinelai.log",
        level=LOG_LEVEL,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | "
            "{name}:{function}:{line} | {message}"
        ),
        rotation="10 MB",      # Rotate when file exceeds 10 MB
        retention="7 days",    # Keep logs for 7 days
        compression="gz",      # Compress rotated logs
        backtrace=True,
        diagnose=True,
        enqueue=True,          # Thread-safe async writing
    )

    # ── Separate error-only sink ───────────────────────────────────────────
    logger.add(
        log_dir / "sentinelai_errors.log",
        level="ERROR",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | "
            "{name}:{function}:{line} | {message}"
        ),
        rotation="5 MB",
        retention="30 days",
        compression="gz",
        backtrace=True,
        diagnose=True,
        enqueue=True,
    )

    logger.info(
        f"Logging initialised | level={LOG_LEVEL} | log_dir={log_dir.resolve()}"
    )
