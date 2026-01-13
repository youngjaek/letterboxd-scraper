"""Shared FastAPI dependencies used across routers."""

from functools import lru_cache
from typing import Iterator

from fastapi import Depends
from sqlalchemy.orm import Session

from letterboxd_scraper.config import Settings, load_settings
from letterboxd_scraper.db.session import get_session


@lru_cache(maxsize=1)
def _load_settings() -> Settings:
    return load_settings()


def get_settings() -> Settings:
    return _load_settings()


def get_db_session(settings: Settings = Depends(get_settings)) -> Iterator[Session]:
    with get_session(settings) as session:
        yield session
