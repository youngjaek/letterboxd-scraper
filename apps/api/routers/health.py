from fastapi import APIRouter, Depends

from letterboxd_scraper.config import Settings

from ..dependencies import get_settings


router = APIRouter(prefix="/health", tags=["health"])


@router.get("/", summary="Simple readiness probe")
def read_health(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    return {
        "status": "ok",
        "database_url": settings.database.url.split("@")[-1],
    }
