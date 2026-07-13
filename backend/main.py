"""
SentinelAI — Application Entry Point (v2.0)

Key improvements over v1:
  - Proper logging initialised before anything else.
  - Config validated at startup (missing dirs created, bad values warned).
  - All background tasks centralised in scheduler.py (isolated, error-safe).
  - WebSocket has full error handling and graceful disconnect logging.
  - No print() debugging anywhere — all output goes through loguru.
  - Global exception handler catches any unhandled 500 and logs the traceback.
  - Graceful shutdown via lifespan context manager (replaces deprecated on_event).
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

# ── Bootstrap: logging + config must come first ───────────────────────────────
from core.logging_config import setup_logging
setup_logging()

from config import HEALTH_INTERVAL, validate_config
validate_config()


# ── Lifespan (startup + shutdown) ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages application startup and graceful shutdown.
    All background tasks are started here and cleaned up on shutdown.
    """
    logger.info("=" * 60)
    logger.info("SentinelAI v2.0 starting...")
    logger.info("=" * 60)

    # Synchronize DB tables and columns (creates missing tables and appends missing columns)
    try:
        from database import engine, Base
        from models import tables  # noqa: F401 — ensures all models are registered
        from core.migrator import sync_schema
        
        sync_schema(engine, Base.metadata)
        logger.info("Database schema synchronized and verified.")
    except Exception as exc:
        logger.critical(f"Database initialisation failed: {exc}")
        # Don't exit — let FastAPI start so the user sees an error via API

    # Start mouse/keyboard activity tracking for idle detection
    try:
        from services.activity_service import start_activity_tracking
        start_activity_tracking()
        logger.info("Activity tracking started.")
    except Exception as exc:
        logger.warning(f"Activity tracking failed to start: {exc} (idle detection disabled)")

    # Start all background tasks
    try:
        from services.scheduler import start_all_background_tasks
        start_all_background_tasks()
        logger.info("All background tasks scheduled.")
    except Exception as exc:
        logger.error(f"Background task startup failed: {exc}")

    # Warm the LLM model — loads it into Ollama VRAM before any user arrives.
    # This eliminates the 15-30s first-request cold-start delay.
    # Runs in the background so it doesn't block FastAPI from accepting requests.
    try:
        from services.ollama_client import warm_model
        asyncio.ensure_future(warm_model())
        logger.info("Ollama model warm-up scheduled.")
    except Exception as exc:
        logger.warning(f"Could not schedule model warm-up: {exc}")

    logger.info("SentinelAI is ready. Visit http://localhost:8000/docs")

    yield  # Application is running

    # ── Shutdown ──────────────────────────────────────────────────────────
    logger.info("SentinelAI shutting down...")
    try:
        from services.ollama_client import shutdown as shutdown_ollama
        shutdown_ollama()
    except Exception:
        pass


# ── FastAPI Application ───────────────────────────────────────────────────────

app = FastAPI(
    title       = "SentinelAI",
    description = "Local AI-powered system monitoring and behavioural anomaly detection",
    version     = "2.0.0",
    lifespan    = lifespan,
    docs_url    = "/docs",
    redoc_url   = "/redoc",
)

# CORS — restrict to frontend origin in production
app.add_middleware(
    CORSMiddleware,
    allow_origins    = ["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials= True,
    allow_methods    = ["*"],
    allow_headers    = ["*"],
)


# ── Global Exception Handler ──────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Catches any unhandled exception and returns a structured JSON 500
    instead of exposing raw Python tracebacks to the client.
    """
    logger.error(
        f"Unhandled exception | {request.method} {request.url.path} | "
        f"{type(exc).__name__}: {exc}"
    )
    return JSONResponse(
        status_code = 500,
        content = {
            "error":   "internal_server_error",
            "message": "An unexpected error occurred. Check server logs.",
            "path":    str(request.url.path),
        },
    )


# ── Routers ───────────────────────────────────────────────────────────────────

from routers import alerts, chat, health, reports
from routers.system import router as system_router

app.include_router(health.router)
app.include_router(chat.router)
app.include_router(alerts.router)
app.include_router(reports.router)
app.include_router(system_router)


# ── Root Endpoints ────────────────────────────────────────────────────────────

@app.get("/", tags=["Root"])
def root():
    return {"status": "SentinelAI is running", "version": "2.0.0", "docs": "/docs"}


@app.get("/ping", tags=["Root"])
def ping():
    return {"message": "pong"}


# ── WebSocket: Live Health Feed ───────────────────────────────────────────────

@app.websocket("/ws/health")
async def health_websocket(websocket: WebSocket):
    """
    Streams live CPU/RAM/Disk metrics to the frontend every HEALTH_INTERVAL seconds.

    Error handling:
    - WebSocketDisconnect: logged at DEBUG level (normal client navigation).
    - psutil errors: caught in get_health_metrics(), returns safe defaults.
    - Any other exception: logged as WARNING, connection closed gracefully.
    """
    from services.health_service import get_health_metrics

    client = f"{websocket.client.host}:{websocket.client.port}"
    await websocket.accept()
    logger.debug(f"WebSocket connected | client={client}")

    try:
        while True:
            try:
                data = get_health_metrics()
                await websocket.send_json(data)
            except WebSocketDisconnect:
                raise  # Re-raise to be caught by outer handler
            except Exception as exc:
                logger.warning(f"WebSocket send error | client={client}: {exc}")
                # Try to keep the connection alive on non-fatal errors
            await asyncio.sleep(HEALTH_INTERVAL)

    except WebSocketDisconnect:
        logger.debug(f"WebSocket disconnected | client={client}")
    except Exception as exc:
        logger.warning(f"WebSocket closed unexpectedly | client={client}: {exc}")
    finally:
        try:
            await websocket.close()
        except Exception:
            pass  # Already closed — ignore