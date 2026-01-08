from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Optional

from ..config import Settings
from ..http import ThrottledClient
from .poster_utils import parse_html_document


@dataclass
class PersonDetails:
    slug: str
    tmdb_id: Optional[int]


class PersonPageScraper:
    """Fetch director/person pages to extract TMDB person IDs."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = ThrottledClient(settings)
        self._cache: Dict[str, PersonDetails] = {}

    def fetch_tmdb_id(self, slug: str) -> Optional[int]:
        normalized = slug.strip().strip("/")
        if normalized in self._cache:
            return self._cache[normalized].tmdb_id
        url = f"https://letterboxd.com/director/{normalized}/"
        response = self.client.get(url)
        soup = parse_html_document(response.text)
        tmdb_id = self._extract_tmdb_id(soup)
        details = PersonDetails(slug=normalized, tmdb_id=tmdb_id)
        self._cache[normalized] = details
        return tmdb_id

    def close(self) -> None:
        self.client.close()

    @staticmethod
    def _extract_tmdb_id(soup) -> Optional[int]:
        body = soup.find("body")
        if body:
            tmdb_id = _coerce_int(body.get("data-tmdb-id"))
            if tmdb_id:
                return tmdb_id
        link = soup.find("a", href=re.compile(r"themoviedb\.org/person/(\d+)"))
        if link:
            match = re.search(r"themoviedb\.org/person/(\d+)", link.get("href", ""))
            if match:
                return _coerce_int(match.group(1))
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
