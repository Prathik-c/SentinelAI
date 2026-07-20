"""
SentinelAI — Application Configuration
Typed, validated configuration loaded from environment variables.
All values can be overridden via the .env file or real environment variables.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
import yaml

from dotenv import load_dotenv

load_dotenv()

# ── YAML Configuration ────────────────────────────────────────────────────────
YAML_CONFIG_PATH = os.getenv("SENTINEL_CONFIG", "sentinelai.yaml")
_yaml_config = {}

if os.path.exists(YAML_CONFIG_PATH):
    try:
        with open(YAML_CONFIG_PATH, "r") as f:
            _yaml_config = yaml.safe_load(f) or {}
    except Exception as e:
        print(f"[SentinelAI CONFIG ERROR] Failed to load {YAML_CONFIG_PATH}: {e}", file=sys.stderr)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_nested(keys: list[str], default: any) -> any:
    """Helper to traverse nested dicts (e.g. ['ollama', 'base_url'])"""
    val = _yaml_config
    for key in keys:
        if isinstance(val, dict) and key in val:
            val = val[key]
        else:
            return default
    return val

def _get_val(env_key: str, yaml_keys: list[str], default: any, cast_fn=str) -> any:
    # 1. Try env var
    val = os.getenv(env_key)
    if val is not None:
        try:
            return cast_fn(val)
        except Exception:
            pass
    # 2. Try yaml
    val = _get_nested(yaml_keys, None)
    if val is not None:
        try:
            return cast_fn(val)
        except Exception:
            pass
    # 3. Fallback
    return default

def _get_int(env_key: str, yaml_keys: list[str], default: int) -> int:
    return _get_val(env_key, yaml_keys, default, int)

def _get_float(env_key: str, yaml_keys: list[str], default: float) -> float:
    return _get_val(env_key, yaml_keys, default, float)

def _get_bool(env_key: str, yaml_keys: list[str], default: bool) -> bool:
    val = _get_val(env_key, yaml_keys, default, str).lower()
    return val in ("1", "true", "yes", "on")

def _get_str(env_key: str, yaml_keys: list[str], default: str) -> str:
    return _get_val(env_key, yaml_keys, default, str)

# ── Ollama / LLM ─────────────────────────────────────────────────────────────

OLLAMA_BASE_URL: str   = _get_str("OLLAMA_BASE_URL", ["ollama", "base_url"], "http://localhost:11434")
CHAT_MODEL: str        = _get_str("CHAT_MODEL", ["ollama", "chat_model"], "mistral:7b")
REPORT_MODEL: str      = _get_str("REPORT_MODEL", ["ollama", "report_model"], "mistral:7b")

LLM_TIMEOUT_SECONDS: int = _get_int("LLM_TIMEOUT_SECONDS", ["ollama", "timeout_seconds"], 60)
OLLAMA_KEEP_ALIVE: str = _get_str("OLLAMA_KEEP_ALIVE", ["ollama", "keep_alive"], "24h")
LLM_EXECUTOR_THREADS: int = _get_int("LLM_EXECUTOR_THREADS", ["ollama", "executor_threads"], 2)
LLM_SEMAPHORE_LIMIT: int = _get_int("LLM_SEMAPHORE_LIMIT", ["ollama", "semaphore_limit"], 2)

# ── Database ──────────────────────────────────────────────────────────────────

DB_PATH: str = _get_str("DB_PATH", ["database", "path"], "./data/sentinelai.db")

# ── File Paths ────────────────────────────────────────────────────────────────

SNAPSHOTS_PATH: str    = _get_str("SNAPSHOTS_PATH", ["paths", "snapshots"], "./snapshots")
KNOWN_FACES_PATH: str  = _get_str("KNOWN_FACES_PATH", ["paths", "known_faces"], "./known_faces")
REPORTS_DIR: str       = _get_str("REPORTS_DIR", ["paths", "reports"], "./data/reports")
LOGS_DIR: str          = _get_str("LOGS_DIR", ["logging", "dir"], "./logs")

# ── Health Monitoring ─────────────────────────────────────────────────────────

HEALTH_INTERVAL: int   = _get_int("HEALTH_CHECK_INTERVAL", ["system", "health_interval_seconds"], 2)
LOG_INTERVAL: int      = _get_int("LOG_INTERVAL_SECONDS", ["system", "log_interval_seconds"], 60)

# ── Baseline & Anomaly Detection ──────────────────────────────────────────────

MIN_BASELINE_SAMPLES: int = _get_int("MIN_BASELINE_SAMPLES", ["behavior", "min_baseline_samples"], 15)
KNOWN_PROCESS_THRESHOLD: float = _get_float("KNOWN_PROCESS_THRESHOLD", ["behavior", "known_process_threshold"], 0.05)
CPU_ANOMALY_MULTIPLIER: float = _get_float("CPU_ANOMALY_MULTIPLIER", ["behavior", "cpu_anomaly_multiplier"], 3.0)
RAM_ANOMALY_MARGIN: float = _get_float("RAM_ANOMALY_MARGIN", ["behavior", "ram_anomaly_margin"], 20.0)
MAX_LOG_CONTEXT_ROWS: int = _get_int("MAX_LOG_CONTEXT_ROWS", ["behavior", "max_log_context_rows"], 10)
BASELINE_CACHE_TTL: int = _get_int("BASELINE_CACHE_TTL_SECONDS", ["behavior", "baseline_cache_ttl"], 300)

# ── Background Scheduler ──────────────────────────────────────────────────────

ANOMALY_CHECK_INTERVAL: int = _get_int("ANOMALY_CHECK_INTERVAL_SECONDS", ["behavior", "anomaly_engine_interval"], 300)
BASELINE_UPDATE_INTERVAL: int = _get_int("BASELINE_UPDATE_INTERVAL_SECONDS", ["behavior", "baseline_update_interval"], 3600)
REPORT_INTERVAL_DAYS: int = _get_int("REPORT_INTERVAL_DAYS", ["behavior", "report_interval_days"], 7)

# ── Logging ───────────────────────────────────────────────────────────────────

LOG_LEVEL: str = _get_str("LOG_LEVEL", ["logging", "level"], "INFO").upper()

# ── Other ─────────────────────────────────────────────────────────────────────

FACE_SCAN_INTERVAL: int = _get_int("FACE_SCAN_INTERVAL", ["system", "face_scan_interval"], 1)
FACE_INTERVAL = FACE_SCAN_INTERVAL


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