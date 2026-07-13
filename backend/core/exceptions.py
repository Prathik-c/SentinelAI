"""
SentinelAI — Custom Exception Hierarchy

Defines application-specific exceptions so callers can catch specific failure
modes rather than bare ``Exception`` and provide meaningful user feedback.
All exceptions carry an optional ``detail`` string for API responses.
"""
from __future__ import annotations


class SentinelAIError(Exception):
    """Base class for all SentinelAI exceptions."""

    def __init__(self, message: str = "", detail: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or message


# ── LLM / Ollama ──────────────────────────────────────────────────────────────

class LLMTimeoutError(SentinelAIError):
    """Raised when an Ollama request exceeds LLM_TIMEOUT_SECONDS."""

    def __init__(self, model: str = "", timeout: int = 0) -> None:
        msg = (
            f"Ollama model '{model}' did not respond within {timeout}s. "
            "The model may be loading or the system is under load."
        )
        super().__init__(msg)


class OllamaUnavailableError(SentinelAIError):
    """Raised when the Ollama HTTP server cannot be reached at all."""

    def __init__(self, url: str = "") -> None:
        msg = (
            f"Cannot connect to Ollama at '{url}'. "
            "Ensure Ollama is running: `ollama serve`"
        )
        super().__init__(msg)


class LLMResponseError(SentinelAIError):
    """Raised when Ollama returns an unexpected or malformed response."""


# ── Database ──────────────────────────────────────────────────────────────────

class DatabaseLockError(SentinelAIError):
    """Raised when SQLite busy_timeout is exceeded (write lock not released)."""

    def __init__(self) -> None:
        super().__init__(
            "Database is temporarily locked by another process. "
            "The request will be retried automatically."
        )


class DatabaseReadError(SentinelAIError):
    """Raised when a database query returns unexpected / malformed data."""


# ── Baseline & Anomaly ────────────────────────────────────────────────────────

class BaselineNotReadyError(SentinelAIError):
    """
    Raised when anomaly detection is requested but not enough health log
    samples have been collected to compute a reliable baseline.
    """

    def __init__(self, current: int, required: int) -> None:
        msg = (
            f"Baseline not ready: have {current} samples, "
            f"need at least {required}. "
            "SentinelAI is still learning your system's normal behaviour."
        )
        super().__init__(msg)
        self.current = current
        self.required = required


# ── Reports ───────────────────────────────────────────────────────────────────

class ReportGenerationError(SentinelAIError):
    """Raised when PDF or HTML report generation fails."""


# ── Intent / RAG ─────────────────────────────────────────────────────────────

class IntentClassificationError(SentinelAIError):
    """Raised when intent classification produces an unexpected result."""
