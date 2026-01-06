from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import unquote

from bs4.element import Tag

from ..config import Settings
from ..http import ThrottledClient
from .poster_utils import parse_html_document


@dataclass
class HistogramBucket:
    bucket_label: str
    rating_value: float
    count: int
    percentage: float


@dataclass
class HistogramSummary:
    slug: str
    weighted_average: Optional[float]
    rating_count: Optional[int]
    fan_count: Optional[int]
    buckets: List[HistogramBucket]


class RatingsHistogramScraper:
    """Fetch Letterboxd ratings histogram summaries for global stats."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = ThrottledClient(settings)

    def fetch(self, slug: str) -> HistogramSummary:
        normalized = slug.strip().strip("/")
        url = f"https://letterboxd.com/csi/film/{normalized}/ratings-summary/"
        response = self.client.get(url)
        return self.parse_html(normalized, response.text)

    def close(self) -> None:
        self.client.close()

    @staticmethod
    def parse_html(slug: str, html: str) -> HistogramSummary:
        soup = parse_html_document(html)
        section = soup.find("section", class_="ratings-histogram-chart")
        weighted_average, rating_count = RatingsHistogramScraper._parse_average(section)
        fan_count = RatingsHistogramScraper._parse_fan_count(section)
        buckets = RatingsHistogramScraper._parse_buckets(section)
        return HistogramSummary(
            slug=slug,
            weighted_average=weighted_average,
            rating_count=rating_count,
            fan_count=fan_count,
            buckets=buckets,
        )

    @staticmethod
    def _parse_average(section: Optional[Tag]) -> tuple[Optional[float], Optional[int]]:
        if not section:
            return None, None
        node = section.select_one(".average-rating a[title]")
        if not node:
            return None, None
        title = node.get("title") or ""
        match = re.search(
            r"Weighted average of ([\d.]+) based on ([\d,]+) ratings", title
        )
        if not match:
            return None, None
        avg = float(match.group(1))
        count = int(match.group(2).replace(",", ""))
        return avg, count

    @staticmethod
    def _parse_fan_count(section: Optional[Tag]) -> Optional[int]:
        if not section:
            return None
        fan_link = section.select_one(".more-link")
        if not fan_link:
            return None
        text = fan_link.get_text(strip=True)
        match = re.search(r"([\d.,]+)\s*(K|M)?", text, re.IGNORECASE)
        if not match:
            return None
        value = float(match.group(1).replace(",", ""))
        suffix = (match.group(2) or "").upper()
        if suffix == "K":
            value *= 1_000
        elif suffix == "M":
            value *= 1_000_000
        return int(value)

    @staticmethod
    def _parse_buckets(section: Optional[Tag]) -> List[HistogramBucket]:
        if not section:
            return []
        buckets: List[HistogramBucket] = []
        for li in section.select("li.rating-histogram-bar"):
            link = li.find("a")
            if not link:
                continue
            title = link.get("title") or link.get_text(strip=True)
            count = _extract_int(title)
            percentage = _extract_percentage(title)
            rating_value = _extract_rating_value(link.get("href", ""))
            if count is None or rating_value is None or percentage is None:
                continue
            buckets.append(
                HistogramBucket(
                    bucket_label=f"{rating_value:g}",
                    rating_value=rating_value,
                    count=count,
                    percentage=percentage,
                )
            )
        return buckets


def _extract_int(text: str) -> Optional[int]:
    match = re.search(r"([\d,]+)", text)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def _extract_percentage(text: str) -> Optional[float]:
    match = re.search(r"\(([\d.]+)%\)", text)
    if not match:
        return None
    return float(match.group(1))


def _extract_rating_value(href: str) -> Optional[float]:
    match = re.search(r"/rated/([^/]+)/", href)
    if not match:
        return None
    value = unquote(match.group(1))
    value = value.replace(" ", "")
    if value.endswith("½"):
        base = value[:-1] or "0"
        return float(base) + 0.5
    try:
        return float(value)
    except ValueError:
        return None
