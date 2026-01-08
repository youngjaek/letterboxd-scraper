from __future__ import annotations

import re
from typing import List, Optional, Sequence
from urllib.parse import urlparse

from bs4 import BeautifulSoup, FeatureNotFound
from bs4.element import Tag


def parse_html_document(html: str) -> BeautifulSoup:
    """
    Parse raw HTML into a BeautifulSoup document.

    Handles both "view-source" exports (wrapped in <td class="line-content">)
    and regular HTML pages by detecting those line blocks and re-parsing the
    concatenated text once tags such as <span class="html-tag"> are stripped.
    """

    def _to_soup(source: str) -> BeautifulSoup:
        for parser in ("lxml", "html.parser"):
            try:
                return BeautifulSoup(source, parser)
            except FeatureNotFound:
                continue
        raise FeatureNotFound("Install lxml or html5lib for better parsing support.")

    soup = _to_soup(html)
    line_blocks = soup.select("td.line-content")
    if line_blocks:
        cleaned = "".join(block.get_text() for block in line_blocks)
        cleaned = re.sub(r"</?span[^>]*>", "", cleaned)
        soup = _to_soup(cleaned)
    return soup


def find_poster_entries(soup: BeautifulSoup) -> List[Tag]:
    """
    Return elements that represent poster/list entries.

    The HTML varies between pages (profile grids, lists, filmography). We try a
    handful of selectors and fall back to any element that exposes film slug
    metadata.
    """
    selectors = [
        "li.poster-container",
        "div.poster-grid li.griditem",
        "li.listitem",
        "ul.poster-list li",
    ]
    seen: set[int] = set()
    results: List[Tag] = []
    for selector in selectors:
        for node in soup.select(selector):
            if id(node) in seen:
                continue
            seen.add(id(node))
            results.append(node)
    if results:
        return results
    fallback = soup.select("[data-film-slug], [data-item-slug]")
    deduped: List[Tag] = []
    for node in fallback:
        if id(node) in seen:
            continue
        seen.add(id(node))
        deduped.append(node)
    return deduped


def extract_film_metadata(film: Tag) -> tuple[Optional[str], Optional[str], Optional[int]]:
    slug = film.get("data-film-slug")
    title = film.get("data-film-name") or film.get("data-film-title")
    letterboxd_id = _coerce_int(film.get("data-film-id"))
    img = film.find("img", alt=True)
    if img:
        title = img.get("alt") or title
    div_with_slug = film.find("div", attrs={"data-film-slug": True})
    if div_with_slug:
        slug = slug or div_with_slug.get("data-film-slug")
        letterboxd_id = letterboxd_id or _coerce_int(div_with_slug.get("data-film-id"))
    embedded = film.find(attrs={"data-item-slug": True})
    if embedded:
        slug = slug or embedded.get("data-item-slug")
        title = title or embedded.get("data-item-name")
        letterboxd_id = letterboxd_id or _coerce_int(embedded.get("data-film-id"))
        slug = slug or slug_from_link(
            embedded.get("data-item-link") or embedded.get("data-target-link")
        )
    candidate_with_id = film.find(attrs={"data-film-id": True})
    if candidate_with_id and not letterboxd_id:
        letterboxd_id = _coerce_int(candidate_with_id.get("data-film-id"))
    if not slug:
        link = film.find("a", href=True)
        if link:
            slug = slug_from_link(link["href"])
    return slug, title, letterboxd_id


def slug_from_link(link: Optional[str]) -> Optional[str]:
    if not link:
        return None
    link = link.strip()
    if not link:
        return None
    parsed = urlparse(link)
    path = parsed.path if parsed.scheme else link
    path = path.split("?")[0].strip("/")
    parts = path.split("/")
    if not parts:
        return None
    if parts[0] in {"film", "director"} and len(parts) >= 2:
        return parts[1]
    return None


def extract_year(film: Tag, fallbacks: Sequence[str] = ()) -> Optional[int]:
    """Best-effort helper to pull a release year from poster metadata."""
    for attr in ("data-film-release-year", "data-year", "data-film-year"):
        value = film.get(attr)
        if value:
            year = _coerce_year(value)
            if year:
                return year
    candidate = film.find(attrs={"data-film-release-year": True})
    if candidate:
        year = _coerce_year(candidate.get("data-film-release-year"))
        if year:
            return year
    for attr in ("data-film-name", "data-item-name", "data-film-title"):
        nested = film.find(attrs={attr: True})
        if nested:
            year = _year_from_text(nested.get(attr))
            if year:
                return year
    for text in fallbacks:
        year = _year_from_text(text)
        if year:
            return year
    return None


def _coerce_year(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    try:
        year = int(value)
    except ValueError:
        return None
    if 1800 <= year <= 2100:
        return year
    return None


def _year_from_text(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    match = re.search(r"(18|19|20)\d{2}", text)
    if not match:
        return None
    return _coerce_year(match.group(0))


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
