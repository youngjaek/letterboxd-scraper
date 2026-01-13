from fastapi import APIRouter, Depends

from ..dependencies import get_settings
from letterboxd_scraper.config import Settings


router = APIRouter(prefix="/health", tags=["health"])


@router.get("/", summary="Simple readiness probe")
def read_health(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    return {
        "status": "ok",
        "database_url": settings.database.url.split("@")[-1],
    }
