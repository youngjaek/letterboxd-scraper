from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

import httpx
from bs4 import BeautifulSoup, FeatureNotFound
from bs4.element import Tag

from ..config import Settings
from ..http import ThrottledClient


@dataclass
class FilmRating:
    film_slug: str
    film_title: str
    rating: float
    rated_at: Optional[str] = None


class ProfileRatingsScraper:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = ThrottledClient(settings)

    @staticmethod
    def _parse_html(html: str) -> BeautifulSoup:
        for parser in ("lxml", "html.parser"):
            try:
                return BeautifulSoup(html, parser)
            except FeatureNotFound:
                continue
        raise FeatureNotFound("Install lxml or html5lib for better parsing support.")

    def fetch_user_ratings(self, username: str) -> Iterable[FilmRating]:
        page = 1
        while True:
            url = f"https://letterboxd.com/{username}/films/rated/.5-5/page/{page}/"
            response = self.client.get(url)
            soup = self._parse_html(response.text)
            films = self._find_film_entries(soup)
            if not films:
                break
            for film in films:
                slug, title = self._extract_film_metadata(film)
                if not slug or not title:
                    continue
                rating_element = (
                    film.select_one("p.poster-viewingdata span.rating")
                    or film.find("span", class_="rating")
                )
                rating_value = self._extract_rating_value(film, rating_element)
                if rating_value is None:
                    continue
                yield FilmRating(film_slug=slug, film_title=title, rating=rating_value)
            page += 1

    def close(self) -> None:
        self.client.close()

    @staticmethod
    def _find_film_entries(soup: BeautifulSoup) -> List[Tag]:
        legacy = soup.find_all("li", class_="poster-container")
        if legacy:
            return legacy
        return soup.select("div.poster-grid li.griditem")

    @staticmethod
    def _extract_film_metadata(film: Tag) -> tuple[Optional[str], Optional[str]]:
        slug = film.get("data-film-slug")
        title = film.get("data-film-name")
        img = film.find("img", alt=True)
        if img:
            title = img.get("alt") or title
        div_with_slug = film.find("div", attrs={"data-film-slug": True})
        if div_with_slug:
            slug = slug or div_with_slug.get("data-film-slug")
        embedded = film.find(attrs={"data-item-slug": True})
        if embedded:
            slug = slug or embedded.get("data-item-slug")
            title = title or embedded.get("data-item-name")
            slug = slug or ProfileRatingsScraper._slug_from_link(
                embedded.get("data-item-link") or embedded.get("data-target-link")
            )
        if not slug:
            link = film.find("a", href=True)
            if link:
                slug = ProfileRatingsScraper._slug_from_link(link["href"])
        return slug, title

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
    def _slug_from_link(link: Optional[str]) -> Optional[str]:
        if not link:
            return None
        link = link.strip()
        if not link:
            return None
        link = link.split("?")[0]
        link = link.strip("/")
        parts = link.split("/")
        if not parts:
            return None
        if parts[0] == "film" and len(parts) >= 2:
            return parts[1]
        return None
