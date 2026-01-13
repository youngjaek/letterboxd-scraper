from __future__ import annotations

import secrets
from hashlib import sha256
from typing import Optional

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.orm import Session

from letterboxd_scraper.db import models

from .dependencies import get_db_session

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def _hash_api_key(api_key: str) -> str:
    return sha256(api_key.encode("utf-8")).hexdigest()


def generate_api_key() -> tuple[str, str]:
    key = secrets.token_hex(24)
    return key, _hash_api_key(key)


def require_api_user(
    api_key: Optional[str] = Security(API_KEY_HEADER),
    session: Session = Depends(get_db_session),
) -> models.User:
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key")
    hashed = _hash_api_key(api_key)
    stmt = select(models.User).where(models.User.api_key_hash == hashed)
    user = session.scalars(stmt).one_or_none()
    if not user:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return user
