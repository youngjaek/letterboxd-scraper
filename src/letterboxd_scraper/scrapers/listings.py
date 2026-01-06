from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

import httpx

from ..config import Settings
from ..http import ThrottledClient
from .poster_utils import (
    extract_film_metadata,
    extract_year,
    find_poster_entries,
    parse_html_document,
)


@dataclass
class FilmListEntry:
    slug: str
    title: str
    year: Optional[int] = None
    letterboxd_film_id: Optional[int] = None


class PosterListingScraper:
    """
    Shared scraper for Letterboxd list/filmography pages that expose poster grids.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = ThrottledClient(settings)

    def close(self) -> None:
        self.client.close()

    def iter_list_entries(self, list_path: str) -> Iterable[FilmListEntry]:
        """Iterate entries from a paginated Letterboxd list."""
        yield from self._iter_path(list_path, paged=True)

    def iter_single_page(self, path: str) -> Iterable[FilmListEntry]:
        """Iterate entries from a single page (e.g., filmography)."""
        yield from self._iter_path(path, paged=False)

    def _iter_path(self, path: str, *, paged: bool) -> Iterable[FilmListEntry]:
        path = path.strip("/")
        if not path:
            return
        page = 1
        while True:
            url = self._build_url(path, page if paged else None)
            try:
                response = self.client.get(url)
            except httpx.HTTPStatusError as exc:  # pragma: no cover - handled by tests
                if paged and page > 1 and exc.response.status_code == 404:
                    break
                raise
            entries = self.parse_html(response.text)
            if not entries:
                break
            for entry in entries:
                yield entry
            if not paged:
                break
            page += 1

    @staticmethod
    def parse_html(html: str) -> List[FilmListEntry]:
        soup = parse_html_document(html)
        films = find_poster_entries(soup)
        entries: List[FilmListEntry] = []
        for film in films:
            slug, title, lb_film_id = extract_film_metadata(film)
            if not slug or not title:
                continue
            tooltip = film.get("title")
            entries.append(
                FilmListEntry(
                    slug=slug,
                    title=title,
                    year=extract_year(film, (title, tooltip)),
                    letterboxd_film_id=lb_film_id,
                )
            )
        return entries

    @staticmethod
    def _build_url(path: str, page: Optional[int]) -> str:
        normalized = path.strip()
        if normalized.startswith("http://") or normalized.startswith("https://"):
            base = normalized
        else:
            base = f"https://letterboxd.com/{normalized.strip('/')}/"
        if not base.endswith("/"):
            base += "/"
        if page and page > 1:
            return f"{base}page/{page}/"
        return base
