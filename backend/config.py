from dotenv import load_dotenv
import os

load_dotenv()

OLLAMA_BASE_URL    = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
CHAT_MODEL         = os.getenv("CHAT_MODEL", "mistral:7b")
REPORT_MODEL       = os.getenv("REPORT_MODEL", "mistral:7b")
DB_PATH            = os.getenv("DB_PATH", "./data/sentinelai.db")
SNAPSHOTS_PATH     = os.getenv("SNAPSHOTS_PATH", "./snapshots")
KNOWN_FACES_PATH   = os.getenv("KNOWN_FACES_PATH", "./known_faces")
HEALTH_INTERVAL    = int(os.getenv("HEALTH_CHECK_INTERVAL", 2))
FACE_INTERVAL      = int(os.getenv("FACE_SCAN_INTERVAL", 1))