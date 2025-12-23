from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Tuple

import httpx
from bs4 import BeautifulSoup, FeatureNotFound

from ..config import Settings
from ..http import ThrottledClient


@dataclass
class FollowResult:
    username: str
    display_name: str | None


class FollowGraphScraper:
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

    def fetch_following(self, username: str) -> List[FollowResult]:
        """Scrape the list of accounts a user follows."""
        page = 1
        results: List[FollowResult] = []
        while True:
            url = f"https://letterboxd.com/{username}/following/page/{page}/"
            response = self.client.get(url)
            soup = self._parse_html(response.text)
            people = soup.find_all("div", class_="follow-button-wrapper")
            if not people:
                break
            for person in people:
                results.append(
                    FollowResult(
                        username=person["data-username"],
                        display_name=person.get("data-name"),
                    )
                )
            page += 1
        return results

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
