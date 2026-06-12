from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
import asyncio
from routers import health
from services.health_service import get_health_metrics
from config import HEALTH_INTERVAL

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

app.include_router(health.router)

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