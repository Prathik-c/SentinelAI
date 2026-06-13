import cv2
from deepface import DeepFace
import os
from datetime import datetime
from config import KNOWN_FACES_PATH, SNAPSHOTS_PATH

def check_face(frame):
    """
    Takes a video frame, checks if any face is recognized.
    Returns: dict with 'recognized' bool, 'name' if matched, 'snapshot_path' if not.
    """
    try:
        result = DeepFace.find(
            img_path=frame,
            db_path=KNOWN_FACES_PATH,
            enforce_detection=False,
            silent=True
        )

        # result is a list of dataframes, one per detected face
        if len(result) > 0 and not result[0].empty:
            matched_path = result[0].iloc[0]["identity"]
            name = os.path.basename(os.path.dirname(matched_path))
            return {"recognized": True, "name": name}
        else:
            # No match — save snapshot of unknown face
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            snapshot_path = f"{SNAPSHOTS_PATH}/unknown_{timestamp}.jpg"
            cv2.imwrite(snapshot_path, frame)
            return {"recognized": False, "snapshot_path": snapshot_path}

    except Exception as e:
        return {"recognized": False, "error": str(e)}
    
    
_camera = None

def start_camera():
    global _camera
    if _camera is None:
        _camera = cv2.VideoCapture(0)
    return _camera.isOpened()

def stop_camera():
    global _camera
    if _camera is not None:
        _camera.release()
        _camera = None

def capture_frame():
    global _camera
    if _camera is None or not _camera.isOpened():
        return None
    ret, frame = _camera.read()
    return frame if ret else None