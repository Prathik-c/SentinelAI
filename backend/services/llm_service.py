"""
SentinelAI — LLM Service (Refactored)

Thin delegation layer over the singleton ollama_client module.
All blocking I/O, thread pooling, semaphore management, keep-alive,
and diagnostics are handled in ollama_client.py.

This module retains its public API surface so all existing callers
(incident_engine, report_engine, rag_service) work without changes.

Key improvements over the previous version:
- No more local ThreadPoolExecutor (removed duplication).
- Uses persistent client with connection reuse.
- Per-stage timing logged by ollama_client.chat_async().
- Fallback never returns a 500 — always a friendly string.
"""
from __future__ import annotations

from typing import Any, Dict

from loguru import logger

from config import CHAT_MODEL, LLM_TIMEOUT_SECONDS, REPORT_MODEL
from services.ollama_client import chat_async
from utils.prompt_builder import (
    build_anomaly_prompt,
    build_incident_prompt,
    build_rag_prompt,
    build_weekly_report_prompt,
)


# ── Fallback Messages ─────────────────────────────────────────────────────────

_FALLBACK_EXPLANATION = (
    "⚠️ AI explanation is temporarily unavailable. "
    "Ollama may be loading the model or the system is under high load. "
    "The anomaly has been recorded and can be reviewed in the Alerts panel."
)

_FALLBACK_CHAT = (
    "⚠️ I couldn't process your question right now — "
    "the local AI model may be loading or busy. "
    "Please try again in a few seconds."
)


# ── Public API (unchanged surface) ───────────────────────────────────────────

async def explain_incident_async(incident_dict: Dict[str, Any]) -> str:
    """
    Generates a concise human-readable explanation for a structured incident.
    Called asynchronously after the incident is already saved to DB.
    """
    prompt = build_incident_prompt(incident_dict)
    return await chat_async(
        prompt    = prompt,
        model     = REPORT_MODEL,
        timeout   = LLM_TIMEOUT_SECONDS,
        fallback  = _FALLBACK_EXPLANATION,
    )


async def explain_anomalies_async(anomalies: list, baseline: dict) -> str:
    """
    Backwards-compatible wrapper for the old explain_anomalies() interface.
    Used by any code that still passes raw anomaly lists.
    """
    if not anomalies:
        return "✅ System is operating normally within your established baseline."

    prompt = build_anomaly_prompt(anomalies, baseline)
    return await chat_async(
        prompt    = prompt,
        model     = REPORT_MODEL,
        timeout   = LLM_TIMEOUT_SECONDS,
        fallback  = _FALLBACK_EXPLANATION,
    )


def explain_anomalies(anomalies: list, baseline: dict) -> str:
    """
    Synchronous wrapper for backwards compatibility with existing code that
    calls this from non-async contexts (e.g., background tasks in threads).
    """
    if not anomalies:
        return "✅ System is operating normally within your established baseline."

    import asyncio
    import concurrent.futures
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    explain_anomalies_async(anomalies, baseline),
                )
                return future.result(timeout=LLM_TIMEOUT_SECONDS + 5)
        else:
            return loop.run_until_complete(
                explain_anomalies_async(anomalies, baseline)
            )
    except Exception as exc:
        logger.error(f"explain_anomalies sync wrapper failed: {exc}")
        return _FALLBACK_EXPLANATION


async def answer_question_async(context: str, question: str, intent: str = "") -> str:
    """
    Generates a RAG answer for the user's question given retrieved context.
    """
    prompt = build_rag_prompt(context, question, intent)
    return await chat_async(
        prompt    = prompt,
        model     = CHAT_MODEL,
        timeout   = LLM_TIMEOUT_SECONDS,
        fallback  = _FALLBACK_CHAT,
    )


async def generate_weekly_narrative_async(stats: Dict[str, Any]) -> str:
    """
    Generates a 2–3 paragraph AI narrative for the weekly health report.
    """
    prompt = build_weekly_report_prompt(stats)
    return await chat_async(
        prompt    = prompt,
        model     = REPORT_MODEL,
        timeout   = LLM_TIMEOUT_SECONDS,
        fallback  = (
            "AI narrative generation was unavailable during this report cycle. "
            "All quantitative statistics above are fully accurate and Python-generated."
        ),
    )