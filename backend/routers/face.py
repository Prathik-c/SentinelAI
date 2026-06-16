from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
import asyncio
from database import get_db
from services import face_service, alert_service
from config import FACE_INTERVAL

router = APIRouter(prefix="/face", tags=["Face Detection"])

_monitoring = False

@router.post("/start")
def start_monitoring():
    global _monitoring
    success = face_service.start_camera()
    _monitoring = success
    return {"started": success}

@router.post("/stop")
def stop_monitoring():
    global _monitoring
    _monitoring = False
    face_service.stop_camera()
    return {"stopped": True}

@router.websocket("/ws/alerts")
async def alerts_websocket(websocket: WebSocket, db: Session = Depends(get_db)):
    await websocket.accept()
    try:
        while True:
            if _monitoring:
                frame = face_service.capture_frame()
                print("DEBUG frame:", "captured" if frame is not None else "None")
                if frame is not None:
                    result = face_service.check_face(frame)
                    print("DEBUG result:", result)

                    if not result.get("recognized") and "error" not in result:
                        incident = alert_service.create_incident(
                            db,
                            description="Unknown face detected",
                            snapshot=result.get("snapshot_path"),
                            severity="medium"
                        )
                        alert_service.cleanup_old_snapshots(keep_last=20)
                        await websocket.send_json({
                            "id": incident.id,
                            "type": "face",
                            "description": incident.description,
                            "snapshot": incident.snapshot,
                            "status": incident.status,
                            "timestamp": str(incident.timestamp)
                        })

            await asyncio.sleep(FACE_INTERVAL)
    except WebSocketDisconnect:
        pass