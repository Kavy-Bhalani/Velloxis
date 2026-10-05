import time
from fastapi import APIRouter
from app.core.config import get_settings
from app.db.session import db_manager

router = APIRouter()
settings = get_settings()
_START_TIME = time.time()

@router.get("/health")
async def health_check():
    """
    Health check for Google Cloud Run liveness/readiness probes.
    """
    db_connected = db_manager.pool is not None
    uptime_seconds = int(time.time() - _START_TIME)

    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "database_connected": db_connected,
        "uptime_seconds": uptime_seconds,
    }
