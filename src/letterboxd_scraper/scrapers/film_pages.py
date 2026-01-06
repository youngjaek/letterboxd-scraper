from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Optional, List

from bs4 import BeautifulSoup

from ..config import Settings
from ..http import ThrottledClient
from .poster_utils import parse_html_document


@dataclass
class FilmPageDetails:
    slug: str
    tmdb_id: Optional[int]
    imdb_id: Optional[str]
    letterboxd_film_id: Optional[int]
    release_year: Optional[int] = None
    directors: List[str] = field(default_factory=list)


class FilmPageScraper:
    """Fetch and parse individual Letterboxd film pages for metadata such as TMDB IDs."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = ThrottledClient(settings)
        self._cache: Dict[str, FilmPageDetails] = {}

    def fetch(self, slug: str) -> FilmPageDetails:
        normalized_slug = slug.strip().strip("/")
        if normalized_slug in self._cache:
            return self._cache[normalized_slug]
        url = f"https://letterboxd.com/film/{normalized_slug}/"
        response = self.client.get(url)
        soup = parse_html_document(response.text)
        details = FilmPageDetails(
            slug=normalized_slug,
            tmdb_id=self._extract_tmdb_id(soup),
            imdb_id=self._extract_imdb_id(soup),
            letterboxd_film_id=self._extract_letterboxd_id(soup),
            release_year=self._extract_release_year(soup),
            directors=self._extract_directors(soup),
        )
        self._cache[normalized_slug] = details
        return details

    def close(self) -> None:
        self.client.close()

    @staticmethod
    def _extract_tmdb_id(soup: BeautifulSoup) -> Optional[int]:
        body = soup.find("body")
        if not body:
            return None
        value = body.get("data-tmdb-id")
        return _coerce_int(value)

    @staticmethod
    def _extract_letterboxd_id(soup: BeautifulSoup) -> Optional[int]:
        body = soup.find("body")
        if not body:
            return None
        return _coerce_int(body.get("data-film-id"))

    @staticmethod
    def _extract_imdb_id(soup: BeautifulSoup) -> Optional[str]:
        link = soup.find("a", href=re.compile(r"imdb\.com/title/(tt\d+)"))
        if not link:
            return None
        match = re.search(r"(tt\d+)", link.get("href", ""))
        return match.group(1) if match else None

    @staticmethod
    def _extract_release_year(soup: BeautifulSoup) -> Optional[int]:
        title = soup.find("h1", class_=re.compile("headline"))
        if title:
            year_link = title.find("small")
            if year_link:
                year = _coerce_int(year_link.get_text(strip=True))
                if year:
                    return year
        release_span = soup.select_one(".productioninfo .releasedate")
        if release_span:
            link = release_span.find("a")
            text = link.get_text(strip=True) if link else release_span.get_text(strip=True)
            year = _coerce_int(text)
            if year:
                return year
        return None

    @staticmethod
    def _extract_directors(soup: BeautifulSoup) -> List[str]:
        names: List[str] = []
        seen: set[str] = set()
        credits = soup.select('a[href*="/director/"]')
        for link in credits:
            text = link.get_text(strip=True)
            if not text or text in seen:
                continue
            seen.add(text)
            names.append(text)
        return names


def _coerce_int(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    if ":" in value:
        value = value.split(":")[-1]
    try:
        return int(value)
    except ValueError:
        return None
