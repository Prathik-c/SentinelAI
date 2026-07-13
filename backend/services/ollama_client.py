"""
SentinelAI — Persistent Ollama Client (Singleton)

Solves three core performance problems:

1. CONNECTION REUSE: One OllamaClient instance = one persistent HTTP session.
   No per-request TCP handshake overhead.

2. MODEL KEEP-ALIVE: keep_alive="-1" instructs Ollama to never evict the
   model from VRAM/RAM. First-request cold-start latency is eliminated after
   warm_model() runs at startup.

3. NON-BLOCKING: All calls run in a dedicated thread pool (_llm_executor).
   The FastAPI event loop is NEVER blocked. WebSocket/ping/health endpoints
   remain responsive even when Mistral is mid-generation.

4. CONCURRENCY LIMIT: An asyncio.Semaphore caps simultaneous LLM calls.
   Extra requests queue gracefully instead of spawning unbounded threads.

5. DIAGNOSTICS: get_llm_status() returns real-time model state without
   making a full inference call.
"""
from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, AsyncIterator, Dict, Optional

import ollama
from loguru import logger

from config import (
    CHAT_MODEL,
    LLM_EXECUTOR_THREADS,
    LLM_SEMAPHORE_LIMIT,
    LLM_TIMEOUT_SECONDS,
    OLLAMA_BASE_URL,
    OLLAMA_KEEP_ALIVE,
    REPORT_MODEL,
)


# ── Singleton State ───────────────────────────────────────────────────────────

# One persistent client — reuses the underlying httpx connection pool.
_client: Optional[ollama.Client] = None

# Dedicated thread pool — only LLM calls go here, never health/ws/db tasks.
_llm_executor: Optional[ThreadPoolExecutor] = None

# Async semaphore — prevents more than N simultaneous blocking LLM threads.
_llm_semaphore: Optional[asyncio.Semaphore] = None

# Runtime diagnostics
_stats = {
    "total_calls": 0,
    "total_errors": 0,
    "last_call_at": None,
    "last_latency_ms": None,
    "model_warmed": False,
    "warm_at": None,
}


# ── Initialisation ────────────────────────────────────────────────────────────

def get_client() -> ollama.Client:
    """
    Returns the singleton Ollama client, creating it on first call.
    The client reuses an internal httpx.Client for connection pooling.
    """
    global _client
    if _client is None:
        _client = ollama.Client(host=OLLAMA_BASE_URL)
        logger.debug(f"Ollama singleton client created | host={OLLAMA_BASE_URL}")
    return _client


def get_executor() -> ThreadPoolExecutor:
    """Returns the dedicated LLM thread pool executor."""
    global _llm_executor
    if _llm_executor is None:
        _llm_executor = ThreadPoolExecutor(
            max_workers=LLM_EXECUTOR_THREADS,
            thread_name_prefix="sentinel-llm",
        )
        logger.debug(f"LLM executor created | max_workers={LLM_EXECUTOR_THREADS}")
    return _llm_executor


def get_semaphore() -> asyncio.Semaphore:
    """Returns the async semaphore that caps concurrent LLM calls."""
    global _llm_semaphore
    if _llm_semaphore is None:
        _llm_semaphore = asyncio.Semaphore(LLM_SEMAPHORE_LIMIT)
        logger.debug(f"LLM semaphore created | limit={LLM_SEMAPHORE_LIMIT}")
    return _llm_semaphore


# ── Model Warm-up ─────────────────────────────────────────────────────────────

async def warm_model() -> bool:
    """
    Sends a minimal prompt to Ollama during FastAPI startup.

    WHY: Ollama lazy-loads models on first request. Without warm-up,
    the first user query triggers a 15–30s model load, which either
    times out or makes the system feel broken.

    WITH warm-up: model is in VRAM before any user arrives.
    keep_alive="-1" ensures it stays loaded indefinitely.

    Returns True on success, False if Ollama is unreachable.
    """
    global _stats

    logger.info(f"Warming model '{CHAT_MODEL}' — this may take 10–30s on first run...")
    start = time.monotonic()

    loop = asyncio.get_event_loop()

    def _warm():
        client = get_client()
        client.chat(
            model=CHAT_MODEL,
            messages=[{"role": "user", "content": "ping"}],
            options={"num_predict": 1},  # Generate exactly 1 token — minimal cost
            keep_alive=OLLAMA_KEEP_ALIVE,
        )

    try:
        await asyncio.wait_for(
            loop.run_in_executor(get_executor(), _warm),
            timeout=60.0,  # Generous timeout — model download may be needed
        )
        elapsed = time.monotonic() - start
        _stats["model_warmed"] = True
        _stats["warm_at"] = time.time()
        logger.success(
            f"Model '{CHAT_MODEL}' warmed and loaded | elapsed={elapsed:.1f}s"
        )
        return True

    except asyncio.TimeoutError:
        logger.warning("Model warm-up timed out after 60s. Ollama may be loading.")
        return False
    except Exception as exc:
        logger.warning(f"Model warm-up failed: {exc}. Chat will work once Ollama is ready.")
        return False


# ── Core Async Chat Call ──────────────────────────────────────────────────────

async def chat_async(
    prompt: str,
    model: str = CHAT_MODEL,
    timeout: int = LLM_TIMEOUT_SECONDS,
    fallback: str = "⚠️ AI is temporarily unavailable.",
) -> str:
    """
    Non-blocking async wrapper around ollama.Client.chat().

    Flow:
      1. Acquire semaphore (queues if at capacity — no thread starvation)
      2. Run blocking chat() in the dedicated LLM thread pool
      3. Release semaphore when done (even on error)
      4. Return response text or fallback on any failure

    The FastAPI event loop is NEVER blocked here — only the LLM thread blocks.
    """
    global _stats

    sem = get_semaphore()
    loop = asyncio.get_event_loop()
    start = time.monotonic()

    def _blocking_chat() -> str:
        client = get_client()
        response = client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            keep_alive=OLLAMA_KEEP_ALIVE,
        )
        return response["message"]["content"]

    async with sem:  # Queue if max concurrent calls reached
        _stats["total_calls"] += 1
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(get_executor(), _blocking_chat),
                timeout=float(timeout),
            )
            elapsed_ms = (time.monotonic() - start) * 1000
            _stats["last_call_at"] = time.time()
            _stats["last_latency_ms"] = round(elapsed_ms, 1)

            logger.info(
                f"LLM inference complete | model={model} | "
                f"prompt_chars={len(prompt)} | latency={elapsed_ms:.0f}ms"
            )
            return result

        except asyncio.TimeoutError:
            elapsed = time.monotonic() - start
            _stats["total_errors"] += 1
            logger.warning(
                f"LLM timeout | model={model} | timeout={timeout}s | "
                f"elapsed={elapsed:.1f}s"
            )
            return fallback

        except Exception as exc:
            _stats["total_errors"] += 1
            if "connection" in str(exc).lower() or "refused" in str(exc).lower():
                logger.error(f"Ollama unreachable: {exc}")
            else:
                logger.error(f"LLM error | model={model} | {exc}")
            return fallback


# ── Diagnostics ───────────────────────────────────────────────────────────────

def get_llm_status() -> Dict[str, Any]:
    """
    Returns real-time LLM operational diagnostics without making an inference call.
    Safe to call from the /system/llm endpoint at any frequency.
    """
    import psutil

    # Check Ollama process memory (non-blocking — psutil is fast)
    ollama_mem_mb = None
    try:
        for proc in psutil.process_iter(["name", "memory_info"]):
            if "ollama" in (proc.info.get("name") or "").lower():
                mem = proc.info.get("memory_info")
                if mem:
                    ollama_mem_mb = round(mem.rss / 1024 / 1024, 1)
                    break
    except Exception:
        pass

    sem = get_semaphore()
    # asyncio.Semaphore._value is the remaining capacity (internal, but stable)
    try:
        active_calls = LLM_SEMAPHORE_LIMIT - sem._value  # type: ignore[attr-defined]
    except Exception:
        active_calls = None

    return {
        "model": CHAT_MODEL,
        "report_model": REPORT_MODEL,
        "ollama_url": OLLAMA_BASE_URL,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "model_warmed": _stats["model_warmed"],
        "warm_at": _stats["warm_at"],
        "total_calls": _stats["total_calls"],
        "total_errors": _stats["total_errors"],
        "last_call_at": _stats["last_call_at"],
        "last_latency_ms": _stats["last_latency_ms"],
        "active_calls": active_calls,
        "max_concurrent": LLM_SEMAPHORE_LIMIT,
        "executor_threads": LLM_EXECUTOR_THREADS,
        "ollama_process_mem_mb": ollama_mem_mb,
    }


# ── Graceful Shutdown ─────────────────────────────────────────────────────────

def shutdown() -> None:
    """Shuts down the LLM thread pool. Called during FastAPI lifespan teardown."""
    global _llm_executor
    if _llm_executor:
        _llm_executor.shutdown(wait=False)
        logger.info("LLM thread pool shut down.")
