from fastapi import APIRouter
from app.api.v1.endpoints import generation, credits, ssv, config, report, health

api_router = APIRouter()

api_router.include_router(health.router, tags=["Health"])
api_router.include_router(config.router, tags=["Configuration"])
api_router.include_router(credits.router, tags=["Credits"])
api_router.include_router(generation.router, tags=["Generation"])
api_router.include_router(ssv.router, tags=["AdMob SSV"])
api_router.include_router(report.router, tags=["Reporting"])
