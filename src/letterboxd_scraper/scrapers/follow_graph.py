from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

import httpx
from bs4 import BeautifulSoup

from ..config import Settings
from ..http import ThrottledClient
from .poster_utils import parse_html_document, slug_from_link


@dataclass
class FollowResult:
    username: str
    display_name: Optional[str]
    avatar_url: Optional[str] = None


class FollowGraphScraper:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = ThrottledClient(settings)

    def fetch_following(self, username: str) -> List[FollowResult]:
        """Scrape the list of accounts a user follows."""
        page = 1
        results: List[FollowResult] = []
        while True:
            url = f"https://letterboxd.com/{username}/following/page/{page}/"
            response = self.client.get(url)
            soup = parse_html_document(response.text)
            people: List[BeautifulSoup] = soup.select("div.follow-button-wrapper")
            if not people:
                break
            for person in people:
                username_value = (person.get("data-username") or "").strip()
                if not username_value:
                    slug = slug_from_link(person.get("data-href") or "")
                    if not slug:
                        link = person.select_one("a[href]")
                        if link:
                            slug = slug_from_link(link.get("href"))
                    username_value = slug or ""
                if not username_value:
                    continue
                display_name = (person.get("data-name") or "").strip()
                if not display_name:
                    name_node = person.select_one(".name") or person.select_one(".real-name")
                    if name_node:
                        display_name = name_node.get_text(strip=True)
                if not display_name:
                    title_node = person.select_one("a.button")
                    fallback_title = None
                    if title_node:
                        fallback_title = title_node.get("data-original-title") or title_node.get("title")
                    title = fallback_title or person.get("data-original-title") or person.get("title") or ""
                    for token in ("Follow", "Unfollow"):
                        if token in title:
                            display_name = (
                                title.split(token, 1)[1].split("|", 1)[0].strip().strip('"')
                            )
                            break
                if not display_name:
                    display_name = username_value
                avatar_url = _normalize_avatar_url(person.get("data-avatar"))
                if not avatar_url:
                    avatar = person.select_one("img")
                    if avatar:
                        raw_avatar = (
                            avatar.get("data-src")
                            or avatar.get("data-fallback")
                            or avatar.get("src")
                        )
                        avatar_url = _normalize_avatar_url(raw_avatar)
                results.append(
                    FollowResult(
                        username=username_value,
                        display_name=display_name,
                        avatar_url=avatar_url,
                    )
                )
            page += 1
        return results

    def fetch_profile_metadata(self, username: str) -> Optional[FollowResult]:
        url = f"https://letterboxd.com/{username}/"
        try:
            response = self.client.get(url)
        except httpx.HTTPError:
            return None
        soup = parse_html_document(response.text)
        display_name = _extract_profile_display_name(soup)
        avatar_url = _normalize_avatar_url(_extract_profile_avatar(soup))
        return FollowResult(
            username=username,
            display_name=display_name or username,
            avatar_url=avatar_url,
        )

    def close(self) -> None:
        self.client.close()


def expand_follow_graph(
    scraper: FollowGraphScraper, seed_username: str, depth: int
) -> Iterable[Tuple[int, FollowResult]]:
    """Breadth-first traversal up to depth."""
    current_level = [seed_username]
    visited = {seed_username}
    for level in range(1, depth + 1):
        next_level: List[str] = []
        for username in current_level:
            for follow in scraper.fetch_following(username):
                yield (level, follow)
                if follow.username not in visited:
                    visited.add(follow.username)
                    next_level.append(follow.username)
        current_level = next_level


def _normalize_avatar_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    return re.sub(r"-0-\d+-0-\d+-crop", "-0-1000-0-1000-crop", url)


def _extract_profile_display_name(soup: BeautifulSoup) -> Optional[str]:
    meta = soup.find("meta", attrs={"property": "og:title"})
    if meta and meta.get("content"):
        raw = meta["content"].strip()
        normalized = raw.replace("’", "'")
        suffix = "'s profile"
        if normalized.lower().endswith(suffix):
            return normalized[: -len(suffix)]
        return raw
    header = soup.select_one(".profile-name") or soup.select_one(".profile-header")
    if header:
        text = header.get_text(strip=True)
        if text:
            return text
    return None


def _extract_profile_avatar(soup: BeautifulSoup) -> Optional[str]:
    meta = soup.find("meta", attrs={"property": "og:image"})
    if meta and meta.get("content"):
        return meta["content"]
    img = soup.select_one(".avatar img")
    if img:
        return img.get("src")
    return None
