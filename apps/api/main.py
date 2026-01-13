"""FastAPI entrypoint for the Letterboxd cohort product layer."""

from fastapi import FastAPI

from letterboxd_scraper.db.session import init_engine

from .dependencies import _load_settings
from .routers import api_router


settings = _load_settings()
init_engine(settings)


app = FastAPI(
    title="Letterboxd Cohort API",
    version="0.1.0",
    description="Private alpha API for cohort management, sync triggers, and ranking reads.",
)
app.include_router(api_router)


@app.get("/", tags=["info"], summary="API metadata")
def read_index() -> dict[str, str]:
    return {
        "message": "Letterboxd Cohort API",
        "documentation": "/docs",
    }
