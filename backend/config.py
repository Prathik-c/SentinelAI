"""
SentinelAI — Application Configuration
Typed, validated configuration loaded from environment variables.
All values can be overridden via the .env file or real environment variables.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, default))
    except (ValueError, TypeError):
        return default


def _get_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, default))
    except (ValueError, TypeError):
        return default


def _get_bool(key: str, default: bool) -> bool:
    val = os.getenv(key, str(default)).lower()
    return val in ("1", "true", "yes", "on")


# ── Ollama / LLM ─────────────────────────────────────────────────────────────

OLLAMA_BASE_URL: str   = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
CHAT_MODEL: str        = os.getenv("CHAT_MODEL", "mistral:7b")
REPORT_MODEL: str      = os.getenv("REPORT_MODEL", "mistral:7b")

# Hard timeout (seconds) for any single Ollama HTTP call.
# If exceeded the endpoint returns a graceful fallback string instead of 500.
LLM_TIMEOUT_SECONDS: int = _get_int("LLM_TIMEOUT_SECONDS", 60)

# How long Ollama keeps the model in VRAM/RAM after the last request.
# "-1" means "forever" — the model stays loaded as long as SentinelAI is running.
OLLAMA_KEEP_ALIVE: str = os.getenv("OLLAMA_KEEP_ALIVE", "24h")

# Number of threads in the dedicated LLM executor pool.
# Keep this at 1–2 to avoid context-switching overhead on the GPU.
LLM_EXECUTOR_THREADS: int = _get_int("LLM_EXECUTOR_THREADS", 2)

# Max simultaneous LLM calls (semaphore limit).
# Extra requests queue instead of spawning unbounded threads.
LLM_SEMAPHORE_LIMIT: int = _get_int("LLM_SEMAPHORE_LIMIT", 2)

# ── Database ──────────────────────────────────────────────────────────────────

DB_PATH: str = os.getenv("DB_PATH", "./data/sentinelai.db")

# ── File Paths ────────────────────────────────────────────────────────────────

SNAPSHOTS_PATH: str    = os.getenv("SNAPSHOTS_PATH", "./snapshots")
KNOWN_FACES_PATH: str  = os.getenv("KNOWN_FACES_PATH", "./known_faces")
REPORTS_DIR: str       = os.getenv("REPORTS_DIR", "./data/reports")
LOGS_DIR: str          = os.getenv("LOGS_DIR", "./logs")

# ── Health Monitoring ─────────────────────────────────────────────────────────

# How often (seconds) the WebSocket pushes live metrics to the frontend.
HEALTH_INTERVAL: int   = _get_int("HEALTH_CHECK_INTERVAL", 2)

# How often (seconds) the background task logs a health snapshot to the DB.
LOG_INTERVAL: int      = _get_int("LOG_INTERVAL_SECONDS", 60)

# ── Baseline & Anomaly Detection ──────────────────────────────────────────────

# Minimum number of health log samples required before baseline is computed.
MIN_BASELINE_SAMPLES: int = _get_int("MIN_BASELINE_SAMPLES", 15)

# A process is "known" if it appeared in at least this fraction of all logs.
KNOWN_PROCESS_THRESHOLD: float = _get_float("KNOWN_PROCESS_THRESHOLD", 0.05)

# Multiplier for CPU anomaly threshold: cpu > mean * multiplier → anomaly.
CPU_ANOMALY_MULTIPLIER: float = _get_float("CPU_ANOMALY_MULTIPLIER", 3.0)

# Additive margin for RAM anomaly: ram > mean + margin → anomaly.
RAM_ANOMALY_MARGIN: float = _get_float("RAM_ANOMALY_MARGIN", 20.0)

# How many RAG context rows to include in LLM prompts (caps token count).
MAX_LOG_CONTEXT_ROWS: int = _get_int("MAX_LOG_CONTEXT_ROWS", 10)

# Baseline cache TTL in seconds (recomputed at most once per this window).
BASELINE_CACHE_TTL: int = _get_int("BASELINE_CACHE_TTL_SECONDS", 300)

# ── Background Scheduler ──────────────────────────────────────────────────────

# How often (seconds) the anomaly check runs in the background.
ANOMALY_CHECK_INTERVAL: int = _get_int("ANOMALY_CHECK_INTERVAL_SECONDS", 300)

# How often (seconds) the baseline is recomputed.
BASELINE_UPDATE_INTERVAL: int = _get_int("BASELINE_UPDATE_INTERVAL_SECONDS", 3600)

# Number of days between automatic weekly reports.
REPORT_INTERVAL_DAYS: int = _get_int("REPORT_INTERVAL_DAYS", 7)

# ── Logging ───────────────────────────────────────────────────────────────────

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

# ── Other ─────────────────────────────────────────────────────────────────────

FACE_INTERVAL: int = _get_int("FACE_SCAN_INTERVAL", 1)


# ── Startup Validation ────────────────────────────────────────────────────────

def validate_config() -> None:
    """
    Runs at application startup to catch misconfiguration early.
    Logs warnings for non-critical issues; exits on fatal problems.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Ensure required directories exist (create if missing)
    for dir_path, name in [
        (DB_PATH, "DB_PATH"),
        (REPORTS_DIR, None),
        (LOGS_DIR, None),
        (SNAPSHOTS_PATH, None),
        (KNOWN_FACES_PATH, None),
    ]:
        # For DB_PATH we need the *parent* directory
        target = Path(dir_path).parent if name == "DB_PATH" else Path(dir_path)
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            warnings.append(f"Cannot create directory {target}: {exc}")

    if LLM_TIMEOUT_SECONDS < 10:
        warnings.append(
            f"LLM_TIMEOUT_SECONDS={LLM_TIMEOUT_SECONDS} is very low; "
            "Ollama responses typically take 5–30s."
        )

    if MIN_BASELINE_SAMPLES < 5:
        warnings.append(
            f"MIN_BASELINE_SAMPLES={MIN_BASELINE_SAMPLES} is very low; "
            "baseline will be unreliable with so few samples."
        )

    # Print all issues (logger not yet configured at this point, use print)
    for w in warnings:
        print(f"[SentinelAI CONFIG WARNING] {w}", file=sys.stderr)

    for e in errors:
        print(f"[SentinelAI CONFIG ERROR] {e}", file=sys.stderr)

    if errors:
        sys.exit(1)