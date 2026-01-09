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
                summary_node = None
                row = person.find_parent("tr")
                if row:
                    summary_node = row.select_one(".person-summary") or row
                if not summary_node:
                    summary_node = person.find_previous("div", class_="person-summary")
                display_name = _extract_display_name(person, username_value, summary_node)
                avatar_url = _extract_avatar_url(person, summary_node)
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


def _first_srcset_url(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    first = value.split(",", 1)[0].strip()
    if not first:
        return None
    return first.split(" ", 1)[0]


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


def _extract_avatar_url(person: BeautifulSoup, context: Optional[BeautifulSoup] = None) -> Optional[str]:
    avatar_url = _normalize_avatar_url(person.get("data-avatar"))
    if avatar_url:
        return avatar_url

    def extract_raw(node: BeautifulSoup) -> Optional[str]:
        raw_avatar = (
            node.get("data-avatar")
            or node.get("data-image")
            or node.get("data-src")
            or node.get("data-fallback")
            or node.get("src")
            or _first_srcset_url(node.get("data-srcset"))
            or _first_srcset_url(node.get("srcset"))
        )
        if raw_avatar:
            return raw_avatar
        style = node.get("style")
        if style:
            match = re.search(r"url\(['\"]?(?P<url>[^'\"\)]+)", style)
            if match:
                return match.group("url")
        return None

    search_nodes: List[BeautifulSoup] = []
    if context:
        search_nodes.append(context)
        search_nodes.extend(context.select("[class], [style], img"))
    search_nodes.append(person)
    search_nodes.extend(person.select(".avatar"))
    search_nodes.extend(person.select("img"))
    search_nodes.extend(
        person.select(
            "[data-avatar], [data-image], [data-src], [data-fallback], [data-srcset], [srcset], [style]"
        )
    )
    seen_ids: set[int] = set()
    for node in search_nodes:
        if id(node) in seen_ids:
            continue
        seen_ids.add(id(node))
        raw_avatar = extract_raw(node)
        if raw_avatar:
            normalized = _normalize_avatar_url(raw_avatar)
            if normalized:
                return normalized
    return None


def _extract_display_name(
    person: BeautifulSoup,
    username: str,
    context: Optional[BeautifulSoup] = None,
) -> str:
    candidates: List[tuple[int, str]] = []

    def normalize(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        return value.replace("\xa0", " ").strip().strip('"')

    def add_candidate(value: Optional[str], priority: int) -> None:
        normalized = normalize(value)
        if normalized:
            candidates.append((priority, normalized))

    def combine_parts(values: Iterable[Optional[str]]) -> Optional[str]:
        normalized_parts: List[str] = []
        for value in values:
            normalized = normalize(value)
            if normalized:
                normalized_parts.append(normalized)
        if normalized_parts:
            return " ".join(normalized_parts)
        return None

    def add_node_candidates(node: BeautifulSoup, base_priority: int) -> None:
        add_candidate(
            combine_parts(
                [
                    node.get("data-given-name"),
                    node.get("data-family-name"),
                ]
            ),
            base_priority,
        )
        given_nodes = [child.get_text(" ", strip=True) for child in node.select(".given-name")]
        family_nodes = [child.get_text(" ", strip=True) for child in node.select(".family-name")]
        combined_dom = combine_parts([*given_nodes, *family_nodes])
        if combined_dom:
            add_candidate(combined_dom, base_priority)
        for real_node in node.select(".real-name"):
            add_candidate(real_node.get_text(" ", strip=True), base_priority)
        for name_node in node.select(".name"):
            add_candidate(name_node.get_text(" ", strip=True), base_priority + 2)
        for img in node.select("img[alt]"):
            add_candidate(img.get("alt"), base_priority)

    if context:
        add_node_candidates(context, 0)
    add_node_candidates(person, 2)
    add_candidate(person.get("data-name"), 3)
    title_node = person.select_one("a.button")
    fallback_title = None
    if title_node:
        fallback_title = title_node.get("data-original-title") or title_node.get("title")
    title = fallback_title or person.get("data-original-title") or person.get("title") or ""
    for token in ("Follow", "Unfollow"):
        if token in title:
            add_candidate(title.split(token, 1)[1].split("|", 1)[0], 1)
            break

    def _matches_username(value: str) -> bool:
        normalized = value.strip().lstrip("@").lower()
        return normalized == username.lower()

    filtered = [cand for cand in candidates if not _matches_username(cand[1])]
    pool = filtered or candidates
    if not pool:
        return username
    best_priority, best_value = pool[0]
    for priority, value in pool[1:]:
        if priority < best_priority or (priority == best_priority and len(value) > len(best_value)):
            best_priority, best_value = priority, value
    return best_value
