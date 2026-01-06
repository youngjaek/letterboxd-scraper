from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from letterboxd_scraper.db import models
from letterboxd_scraper.scrapers.ratings import FilmRating
from letterboxd_scraper.services import ratings as rating_service


def make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    return SessionLocal()


def test_upsert_ratings_persists_like_and_favorite_flags():
    session = make_session()
    payloads = [
        FilmRating(
            film_slug="liked-film",
            film_title="Liked",
            rating=4.0,
            liked=True,
            letterboxd_film_id=4001,
        ),
        FilmRating(
            film_slug="favorite-film",
            film_title="Favorite",
            rating=3.0,
            favorite=True,
            letterboxd_film_id=4002,
        ),
    ]
    rating_service.upsert_ratings(session, "testuser", payloads)
    session.commit()
    stmt = select(models.Rating).order_by(models.Rating.film_id)
    ratings = session.execute(stmt).scalars().all()
    assert len(ratings) == 2
    liked_row = next(row for row in ratings if row.film.slug == "liked-film")
    favorite_row = next(row for row in ratings if row.film.slug == "favorite-film")
    assert liked_row.liked is True
    assert liked_row.favorite is False
    assert favorite_row.liked is False
    assert favorite_row.favorite is True
    session.close()


def test_upsert_ratings_updates_existing_flags():
    session = make_session()
    slug = "toggle-film"
    rating_service.upsert_ratings(
        session,
        "tester",
        [
            FilmRating(
                film_slug=slug,
                film_title="Toggle",
                rating=2.5,
                liked=False,
                favorite=False,
                letterboxd_film_id=4100,
            )
        ],
    )
    session.commit()
    rating_service.upsert_ratings(
        session,
        "tester",
        [
            FilmRating(
                film_slug=slug,
                film_title="Toggle",
                rating=4.5,
                liked=True,
                favorite=True,
                letterboxd_film_id=4100,
            )
        ],
    )
    session.commit()
    stmt = select(models.Rating).join(models.Film).where(models.Film.slug == slug)
    rating = session.execute(stmt).scalar_one()
    assert rating.rating == 4.5
    assert rating.liked is True
    assert rating.favorite is True
    session.close()


def test_letterboxd_film_id_prevents_duplicate_films():
    session = make_session()
    first_slug = "temp-slug"
    new_slug = "final-slug"
    rating_service.upsert_ratings(
        session,
        "slugger",
        [
            FilmRating(
                film_slug=first_slug,
                film_title="Temp",
                rating=3.0,
                letterboxd_film_id="film:6001",
            )
        ],
    )
    session.commit()
    rating_service.upsert_ratings(
        session,
        "slugger",
        [
            FilmRating(
                film_slug=new_slug,
                film_title="Temp",
                rating=3.5,
                letterboxd_film_id=6001,
            )
        ],
    )
    session.commit()
    films = session.execute(select(models.Film)).scalars().all()
    assert len(films) == 1
    assert films[0].slug == new_slug
    session.close()


def test_upsert_ratings_handles_unrated_likes():
    session = make_session()
    rating_service.upsert_ratings(
        session,
        "liker",
        [
            FilmRating(
                film_slug="liked-only",
                film_title="Liked Only",
                rating=None,
                liked=True,
                release_year=2010,
            )
        ],
    )
    session.commit()
    rating = session.execute(select(models.Rating)).scalar_one()
    assert rating.rating is None
    assert rating.liked is True
    film = session.execute(select(models.Film)).scalar_one()
    assert film.release_year == 2010
    session.close()
