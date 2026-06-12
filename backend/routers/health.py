
from fastapi import APIRouter
from services.health_service import get_health_metrics

router = APIRouter(prefix="/health", tags=["Health"])

@router.get("/current")
def current_health():
    return get_health_metrics()