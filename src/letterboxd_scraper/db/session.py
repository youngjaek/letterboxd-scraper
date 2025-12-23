from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings

engine = None
SessionLocal = None


def init_engine(settings: Settings) -> None:
    global engine, SessionLocal
    if engine is None:
        engine = create_engine(
            settings.database.url,
            echo=settings.database.echo,
            pool_size=settings.database.pool_size,
            pool_timeout=settings.database.pool_timeout,
        )
        SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@contextmanager
def get_session(settings: Settings) -> Iterator[Session]:
    if SessionLocal is None:
        init_engine(settings)
    session = SessionLocal()  # type: ignore[call-arg]
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
