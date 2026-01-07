from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Set

import httpx
from bs4.element import Tag

from ..config import Settings
from ..http import ThrottledClient
from .poster_utils import (
    extract_film_metadata,
    extract_year,
    find_poster_entries,
    parse_html_document,
    slug_from_link,
)


@dataclass
class FilmRating:
    film_slug: str
    film_title: str
    rating: Optional[float]
    rated_at: Optional[str] = None
    liked: bool = False
    favorite: bool = False
    letterboxd_film_id: Optional[int] = None
    release_year: Optional[int] = None


class ProfileRatingsScraper:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = ThrottledClient(settings)

    def fetch_user_ratings(
        self,
        username: str,
        sort: Optional[str] = "rated-date",
    ) -> Iterable[FilmRating]:
        favorite_slugs = self._fetch_favorite_slugs(username)
        page = 1
        base_url = f"https://letterboxd.com/{username}/films/rated/.5-5/"
        if sort:
            base_url += f"by/{sort}/"
        while True:
            url = f"{base_url}page/{page}/"
            response = self.client.get(url)
            soup = parse_html_document(response.text)
            films = find_poster_entries(soup)
            if not films:
                break
            for film in films:
                slug, title, lb_film_id = extract_film_metadata(film)
                if not slug or not title:
                    continue
                year_context = []
                for candidate in (
                    film.get("data-film-name"),
                    film.get("data-item-name"),
                    film.get("data-film-title"),
                    title,
                ):
                    if candidate:
                        year_context.append(candidate)
                release_year = extract_year(film, tuple(year_context))
                rating_element = (
                    film.select_one("p.poster-viewingdata span.rating")
                    or film.find("span", class_="rating")
                )
                rating_value = self._extract_rating_value(film, rating_element)
                if rating_value is None:
                    continue
                yield FilmRating(
                    film_slug=slug,
                    film_title=title,
                    rating=rating_value,
                    liked=self._is_liked(film),
                    favorite=(slug in favorite_slugs) or self._is_favorite(film),
                    letterboxd_film_id=lb_film_id,
                    release_year=release_year,
                )
            page += 1

    def fetch_user_liked_films(self, username: str) -> Iterable[FilmRating]:
        page = 1
        while True:
            url = f"https://letterboxd.com/{username}/likes/films/rated/none/page/{page}/"
            response = self.client.get(url)
            soup = parse_html_document(response.text)
            films = find_poster_entries(soup)
            if not films:
                break
            for film in films:
                slug, title, lb_film_id = extract_film_metadata(film)
                if not slug or not title:
                    continue
                year_context = []
                for candidate in (
                    film.get("data-film-name"),
                    film.get("data-item-name"),
                    film.get("data-film-title"),
                    title,
                ):
                    if candidate:
                        year_context.append(candidate)
                release_year = extract_year(film, tuple(year_context))
                yield FilmRating(
                    film_slug=slug,
                    film_title=title,
                    rating=None,
                    liked=True,
                    favorite=self._is_favorite(film),
                    letterboxd_film_id=lb_film_id,
                    release_year=release_year,
                )
            page += 1

    def close(self) -> None:
        self.client.close()

    @staticmethod
    def _extract_rating_value(film: Tag, rating_element: Optional[Tag]) -> Optional[float]:
        """Capture ratings from multiple possible HTML representations."""
        if rating_element:
            rating = ProfileRatingsScraper._rating_from_span(rating_element)
            if rating is not None:
                return rating
        for attr in ("data-rating", "data-average-rating", "data-my-rating", "data-own-rating"):
            rating = ProfileRatingsScraper._coerce_rating(film.get(attr))
            if rating is not None:
                return rating
        return None

    @staticmethod
    def _rating_from_span(element: Tag) -> Optional[float]:
        classes = element.get("class", [])
        for cls in classes:
            if cls.startswith("rated-"):
                try:
                    raw = int(cls.split("-")[-1])
                    return raw / 2.0
                except (ValueError, IndexError):
                    continue
        rating = ProfileRatingsScraper._coerce_rating(
            element.get("data-rating") or element.get("data-value")
        )
        if rating is not None:
                return rating
        return ProfileRatingsScraper._rating_from_star_text(element.get_text(strip=True))

    @staticmethod
    def _coerce_rating(value: Optional[str]) -> Optional[float]:
        if not value:
            return None
        value = value.strip()
        if not value:
            return None
        try:
            rating = float(value)
        except ValueError:
            return None
        if rating > 5.0:
            rating = rating / 2.0
        return rating

    @staticmethod
    def _rating_from_star_text(text: Optional[str]) -> Optional[float]:
        if not text:
            return None
        stars = text.count("★")
        half = "½" in text
        if stars == 0 and not half:
            return None
        rating = float(stars)
        if half:
            rating += 0.5
        return rating

    @staticmethod
    def _is_liked(film: Tag) -> bool:
        """Inspect poster metadata for whether the user liked the film."""
        attr_markers = ("data-liked", "data-like", "data-owner-liked", "data-your-like")
        class_markers = {"icon-liked", "is-liked", "poster-liked", "liked"}
        selectors = (".poster", ".poster-viewingdata", ".like", ".js-like", ".react-component")
        return ProfileRatingsScraper._has_flag(film, attr_markers, class_markers, selectors)

    @staticmethod
    def _is_favorite(film: Tag) -> bool:
        """Inspect poster metadata for whether the user favorited the film."""
        attr_markers = (
            "data-favorite",
            "data-favourited",
            "data-owner-favorite",
            "data-your-favorite",
            "data-favorite-status",
        )
        class_markers = {
            "icon-favorite",
            "icon-favourited",
            "poster-favorite",
            "poster-favourited",
            "is-favorite",
            "is-favourite",
            "favorite",
            "favourite",
        }
        selectors = (
            ".poster",
            ".poster-viewingdata",
            ".poster-ribbon",
            ".js-favorite",
            ".favorite",
        )
        return ProfileRatingsScraper._has_flag(film, attr_markers, class_markers, selectors)

    def _fetch_favorite_slugs(self, username: str) -> Set[str]:
        """Fetch favorite films from the profile landing page."""
        url = f"https://letterboxd.com/{username}/"
        try:
            response = self.client.get(url)
        except httpx.HTTPError:
            return set()
        soup = parse_html_document(response.text)
        selectors = [
            "#favourites",
            "#favorites",
            "section.favourites",
            "section.favorites",
            ".profile-favourites",
            ".profile-favorites",
        ]
        favorite_slugs: Set[str] = set()
        containers = []
        for selector in selectors:
            containers.extend(soup.select(selector))
        if not containers:
            return favorite_slugs
        for container in containers:
            favorite_slugs.update(self._extract_favorite_slugs(container))
        return favorite_slugs

    @staticmethod
    def _extract_favorite_slugs(container: Tag) -> Set[str]:
        slugs: Set[str] = set()
        for node in container.select("[data-film-slug]"):
            slug = (node.get("data-film-slug") or "").strip()
            if slug:
                slugs.add(slug)
        for node in container.select("[data-target-link], [data-item-link], a[href]"):
            slug = slug_from_link(
                node.get("data-target-link")
                or node.get("data-item-link")
                or node.get("href")
            )
            if slug:
                slugs.add(slug)
        return slugs

    @staticmethod
    def _has_flag(
        film: Tag,
        attr_markers: Sequence[str],
        class_markers: set[str],
        selectors: Sequence[str],
    ) -> bool:
        for node in ProfileRatingsScraper._iter_flag_nodes(film, selectors):
            if ProfileRatingsScraper._has_named_class(node, class_markers):
                return True
            if ProfileRatingsScraper._has_truthy_attribute(node, attr_markers):
                return True
        return False

    @staticmethod
    def _iter_flag_nodes(film: Tag, selectors: Sequence[str]) -> Iterable[Tag]:
        yield film
        for selector in selectors:
            for node in film.select(selector):
                yield node

    @staticmethod
    def _has_named_class(tag: Tag, markers: set[str]) -> bool:
        classes = tag.get("class", [])
        if not classes:
            return False
        normalized = {cls.strip().lower() for cls in classes if isinstance(cls, str)}
        return any(marker in normalized for marker in markers)

    @staticmethod
    def _has_truthy_attribute(tag: Tag, names: Sequence[str]) -> bool:
        for name in names:
            raw = tag.get(name)
            if raw is None:
                continue
            if ProfileRatingsScraper._coerce_bool(str(raw)):
                return True
        return False

    @staticmethod
    def _coerce_bool(value: Optional[str]) -> Optional[bool]:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not normalized:
            return None
        if normalized in {"1", "true", "yes", "y", "favorite", "favourite", "liked"}:
            return True
        if normalized in {"0", "false", "no", "n"}:
            return False
        return None
