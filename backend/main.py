from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
import asyncio
from routers import health, face
from services.health_service import get_health_metrics
from config import HEALTH_INTERVAL
from database import engine, Base
from models import tables
from services.activity_service import start_activity_tracking
from routers import health, face, chat

app = FastAPI(
    title="SentinelAI",
    description="Local AI Security & Monitoring System",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)

app.include_router(health.router)
app.include_router(face.router)
app.include_router(chat.router)

async def periodic_health_logger():
    from database import SessionLocal
    from services.health_service import log_health_snapshot

    print("DEBUG: periodic_health_logger started")
    while True:
        print("DEBUG: attempting to log health snapshot")
        db = SessionLocal()
        try:
            log_health_snapshot(db)
            print("DEBUG: log successful")
        except Exception as e:
            print("DEBUG: log FAILED:", e)
        finally:
            db.close()
        await asyncio.sleep(60)


@app.on_event("startup")
async def start_background_tasks():
    start_activity_tracking()
    asyncio.create_task(periodic_health_logger())

@app.get("/")
def root():
    return {"status": "SentinelAI is running"}

@app.get("/ping")
def ping():
    return {"message": "pong"}

@app.websocket("/ws/health")
async def health_websocket(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = get_health_metrics()
            await websocket.send_json(data)
            await asyncio.sleep(HEALTH_INTERVAL)
    except WebSocketDisconnect:
        pass