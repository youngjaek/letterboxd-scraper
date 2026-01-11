from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Optional, List
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from ..config import Settings
from ..http import ThrottledClient
from .poster_utils import parse_html_document, slug_from_link


@dataclass
class PersonCredit:
    name: str
    slug: Optional[str] = None


@dataclass
class FilmPageDetails:
    slug: str
    title: Optional[str]
    tmdb_id: Optional[int]
    imdb_id: Optional[str]
    letterboxd_film_id: Optional[int]
    release_year: Optional[int] = None
    runtime_minutes: Optional[int] = None
    poster_url: Optional[str] = None
    overview: Optional[str] = None
    genres: List[str] = field(default_factory=list)
    directors: List[PersonCredit] = field(default_factory=list)
    tmdb_media_type: Optional[str] = None


class FilmPageScraper:
    """Fetch and parse individual Letterboxd film pages for metadata such as TMDB IDs."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = ThrottledClient(settings)
        self._cache: Dict[str, FilmPageDetails] = {}

    def fetch(self, slug: str, *, letterboxd_id: Optional[int] = None) -> FilmPageDetails:
        normalized_slug = slug.strip().strip("/")
        cache_key = f"id:{letterboxd_id}" if letterboxd_id else f"slug:{normalized_slug}"
        cached = self._cache.get(cache_key)
        if cached:
            return cached
        if letterboxd_id:
            url = f"https://letterboxd.com/film/film:{letterboxd_id}/"
        else:
            url = f"https://letterboxd.com/film/{normalized_slug}/"
        response = self.client.get(url)
        soup = parse_html_document(response.text)
        canonical_slug = self._extract_canonical_slug(response) or normalized_slug
        tmdb_id, tmdb_media_type = self._extract_tmdb_reference(soup)
        details = FilmPageDetails(
            slug=canonical_slug,
            title=self._extract_title(soup),
            tmdb_id=tmdb_id,
            imdb_id=self._extract_imdb_id(soup),
            letterboxd_film_id=self._extract_letterboxd_id(soup),
            release_year=self._extract_release_year(soup),
            runtime_minutes=self._extract_runtime_minutes(soup),
            poster_url=self._extract_poster_url(soup),
            overview=self._extract_overview(soup),
            genres=self._extract_genres(soup),
            directors=self._extract_directors(soup),
            tmdb_media_type=tmdb_media_type,
        )
        self._cache[cache_key] = details
        self._cache[f"slug:{canonical_slug}"] = details
        if details.letterboxd_film_id:
            self._cache[f"id:{details.letterboxd_film_id}"] = details
        return details

    def close(self) -> None:
        self.client.close()

    @staticmethod
    def _extract_canonical_slug(response: httpx.Response) -> Optional[str]:
        parsed = urlparse(str(response.url))
        return slug_from_link(parsed.path)

    @staticmethod
    def _extract_tmdb_reference(soup: BeautifulSoup) -> tuple[Optional[int], Optional[str]]:
        link = soup.find("a", href=re.compile(r"themoviedb\.org/(movie|tv)/(\d+)"))
        if link:
            match = re.search(r"themoviedb\.org/(movie|tv)/(\d+)", link.get("href", ""))
            if match:
                link_type = match.group(1)
                link_id = _coerce_int(match.group(2))
                if link_id:
                    return link_id, link_type
        body = soup.find("body")
        if body:
            tmdb_id = _coerce_int(body.get("data-tmdb-id"))
            if tmdb_id:
                media_type = body.get("data-tmdb-type") or None
                return tmdb_id, media_type
        return None, None

    @staticmethod
    def _extract_letterboxd_id(soup: BeautifulSoup) -> Optional[int]:
        body = soup.find("body")
        if body:
            value = _coerce_int(body.get("data-film-id"))
            if value:
                return value
        node = soup.find(attrs={"data-film-id": True})
        if node:
            return _coerce_int(node.get("data-film-id"))
        return None

    @staticmethod
    def _extract_title(soup: BeautifulSoup) -> Optional[str]:
        heading = soup.find("h1", class_=re.compile("headline"))
        if heading:
            text = heading.get_text(" ", strip=True)
            badge = heading.find("small")
            if badge:
                badge_text = badge.get_text(strip=True)
                if badge_text:
                    text = text.replace(badge_text, "").strip()
            if text:
                return text
        meta = soup.find("meta", attrs={"property": "og:title"})
        if meta and meta.get("content"):
            return meta["content"].strip()
        return None

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
    def _extract_directors(soup: BeautifulSoup) -> List[PersonCredit]:
        credits: List[PersonCredit] = []
        seen: set[tuple[Optional[str], str]] = set()
        for link in soup.select('a[href*="/director/"]'):
            text = link.get_text(strip=True)
            if not text:
                continue
            slug = slug_from_link(link.get("href"))
            key = (slug, text)
            if key in seen:
                continue
            seen.add(key)
            credits.append(PersonCredit(name=text, slug=slug))
        return credits

    @staticmethod
    def _extract_poster_url(soup: BeautifulSoup) -> Optional[str]:
        meta = soup.find("meta", attrs={"property": "og:image"})
        if meta and meta.get("content"):
            return meta["content"]
        img = soup.select_one(".film-poster img")
        if img and img.get("src"):
            return img["src"]
        return None

    @staticmethod
    def _extract_genres(soup: BeautifulSoup) -> List[str]:
        genres: List[str] = []
        for link in soup.select('a[href*="/films/genre/"]'):
            text = link.get_text(strip=True)
            if text and text not in genres:
                genres.append(text)
        return genres

    @staticmethod
    def _extract_overview(soup: BeautifulSoup) -> Optional[str]:
        meta = soup.find("meta", attrs={"property": "og:description"})
        if meta and meta.get("content"):
            return meta["content"].strip()
        synopsis = soup.select_one(".synopsis p")
        if synopsis:
            return synopsis.get_text(strip=True)
        return None

    @staticmethod
    def _extract_overview(soup: BeautifulSoup) -> Optional[str]:
        meta = soup.find("meta", attrs={"property": "og:description"})
        if meta and meta.get("content"):
            return meta["content"].strip()
        synopsis = soup.select_one(".synopsis p")
        if synopsis:
            return synopsis.get_text(strip=True)
        return None

    @staticmethod
    def _extract_runtime_minutes(soup: BeautifulSoup) -> Optional[int]:
        footer = soup.select_one("p.text-link.text-footer")
        if not footer:
            return None
        text = footer.get_text(" ", strip=True)
        match = re.search(r"([\d,]+)\s*(mins|minutes|min)", text, re.IGNORECASE)
        if not match:
            return None
        value = match.group(1).replace(",", "")
        try:
            return int(value)
        except ValueError:
            return None


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
