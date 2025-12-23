from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional
from urllib.parse import urlparse

import feedparser

from ..config import Settings


@dataclass
class RSSEntry:
    film_slug: str
    film_title: str
    rating: Optional[float]
    published: Optional[datetime]


class RSSScraper:
    def __init__(self, settings: Settings):
        self.settings = settings

    def fetch_feed(self, username: str) -> Iterable[RSSEntry]:
        url = f"https://letterboxd.com/{username}/rss/"
        feed = feedparser.parse(url)
        for entry in feed.entries[: self.settings.rss.max_entries]:
            film_slug = self._extract_slug(entry)
            film_title = (
                entry.get("letterboxd_film_title")
                or entry.get("letterboxd_filmtitle")
                or entry.get("title")
            )
            rating_value = (
                entry.get("letterboxd_member_rating")
                or entry.get("letterboxd_memberrating")
            )
            rating = self._coerce_rating(rating_value)
            if rating is None:
                rating = self._rating_from_title(entry.get("title"))
            published = (
                datetime(*entry.published_parsed[:6]) if entry.get("published_parsed") else None
            )
            if not film_slug or not film_title or rating is None:
                continue
            yield RSSEntry(
                film_slug=film_slug,
                film_title=film_title,
                rating=rating,
                published=published,
            )

    @staticmethod
    def _extract_slug(entry: dict) -> Optional[str]:
        slug = entry.get("letterboxd_film_slug") or entry.get("letterboxd_filmslug")
        if slug:
            return slug
        link = entry.get("link")
        if link:
            parsed = urlparse(link)
            parts = [part for part in parsed.path.split("/") if part]
            if "film" in parts:
                idx = parts.index("film")
                if idx + 1 < len(parts):
                    return parts[idx + 1]
        return None

    @staticmethod
    def _coerce_rating(value: Optional[str]) -> Optional[float]:
        if not value:
            return None
        value = value.strip()
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    @staticmethod
    def _rating_from_title(title: Optional[str]) -> Optional[float]:
        if not title:
            return None
        star_section = title.split("-")[-1].strip()
        if not star_section:
            return None
        stars = star_section.count("★")
        if stars == 0 and "½" not in star_section:
            return None
        rating = float(stars)
        if "½" in star_section:
            rating += 0.5
        return rating
