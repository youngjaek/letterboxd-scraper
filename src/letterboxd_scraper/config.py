from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional
import os

try:  # Python 3.11+
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover - fallback for <3.11
    import tomli as tomllib  # type: ignore

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None


@dataclass
class DatabaseSettings:
    url: str
    echo: bool = False
    pool_size: int = 5
    pool_timeout: int = 30


@dataclass
class ScraperSettings:
    user_agent: str
    max_concurrency: int = 4
    request_timeout_seconds: int = 15
    retry_limit: int = 3
    retry_backoff_seconds: int = 2
    throttle_seconds: float = 1.0


@dataclass
class RSSSettings:
    poll_interval_minutes: int = 60
    max_entries: int = 50


@dataclass
class TMDBSettings:
    api_key: Optional[str] = None
    base_url: str = "https://api.themoviedb.org/3"
    image_base_url: str = "https://image.tmdb.org/t/p/original"
    request_timeout_seconds: int = 10


@dataclass
class CohortDefaults:
    include_seed: bool = True
    follow_depth: int = 1
    min_votes: int = 25
    m_value: int = 50


@dataclass
class TaskQueueSettings:
    broker_url: str = "redis://localhost:6379/0"
    result_backend: str = "redis://localhost:6379/1"
    default_queue: str = "default"
    scrape_queue: str = "scrape"
    stats_queue: str = "stats"
    enrichment_queue: str = "enrichment"


@dataclass
class Settings:
    database: DatabaseSettings
    scraper: ScraperSettings
    rss: RSSSettings
    tmdb: TMDBSettings
    cohort_defaults: CohortDefaults
    raw: Dict[str, Any] = field(default_factory=dict)
    task_queue: TaskQueueSettings = field(default_factory=TaskQueueSettings)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "database": self.database.__dict__,
            "scraper": self.scraper.__dict__,
            "rss": self.rss.__dict__,
            "cohort_defaults": self.cohort_defaults.__dict__,
            "task_queue": self.task_queue.__dict__,
        }


def _load_toml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


def load_settings(config_path: Optional[Path] = None) -> Settings:
    """Load configuration from TOML + environment variables."""
    if load_dotenv:
        load_dotenv()

    if config_path is None:
        config_path = Path(__file__).resolve().parents[2] / "config" / "default.toml"

    data = _load_toml(config_path)
    database_cfg = data.get("database", {})
    scraper_cfg = data.get("scraper", {})
    rss_cfg = data.get("rss", {})
    tmdb_cfg = data.get("tmdb", {})
    cohort_cfg = data.get("cohort_defaults", {})
    task_queue_cfg = data.get("task_queue", {})

    db_settings = DatabaseSettings(
        url=os.getenv("DATABASE_URL", database_cfg.get("url", "")),
        echo=bool_from_env("DATABASE_ECHO", database_cfg.get("echo", False)),
        pool_size=int(os.getenv("DATABASE_POOL_SIZE", database_cfg.get("pool_size", 5))),
        pool_timeout=int(os.getenv("DATABASE_POOL_TIMEOUT", database_cfg.get("pool_timeout", 30))),
    )

    scraper_settings = ScraperSettings(
        user_agent=os.getenv("SCRAPER_USER_AGENT", scraper_cfg.get("user_agent", "")),
        max_concurrency=int(os.getenv("SCRAPER_MAX_CONCURRENCY", scraper_cfg.get("max_concurrency", 4))),
        request_timeout_seconds=int(
            os.getenv("SCRAPER_TIMEOUT", scraper_cfg.get("request_timeout_seconds", 15))
        ),
        retry_limit=int(os.getenv("SCRAPER_RETRY_LIMIT", scraper_cfg.get("retry_limit", 3))),
        retry_backoff_seconds=int(
            os.getenv("SCRAPER_RETRY_BACKOFF", scraper_cfg.get("retry_backoff_seconds", 2))
        ),
        throttle_seconds=float(os.getenv("SCRAPER_THROTTLE_SECONDS", scraper_cfg.get("throttle_seconds", 1.0))),
    )

    rss_settings = RSSSettings(
        poll_interval_minutes=int(os.getenv("RSS_POLL_MINUTES", rss_cfg.get("poll_interval_minutes", 60))),
        max_entries=int(os.getenv("RSS_MAX_ENTRIES", rss_cfg.get("max_entries", 50))),
    )

    tmdb_settings = TMDBSettings(
        api_key=os.getenv("TMDB_API_KEY", tmdb_cfg.get("api_key")),
        base_url=os.getenv("TMDB_BASE_URL", tmdb_cfg.get("base_url", "https://api.themoviedb.org/3")),
        image_base_url=os.getenv(
            "TMDB_IMAGE_BASE_URL", tmdb_cfg.get("image_base_url", "https://image.tmdb.org/t/p/original")
        ),
        request_timeout_seconds=int(
            os.getenv("TMDB_TIMEOUT", tmdb_cfg.get("request_timeout_seconds", 10))
        ),
    )

    cohort_settings = CohortDefaults(
        include_seed=bool_from_env("COHORT_INCLUDE_SEED", cohort_cfg.get("include_seed", True)),
        follow_depth=int(os.getenv("COHORT_FOLLOW_DEPTH", cohort_cfg.get("follow_depth", 1))),
        min_votes=int(os.getenv("COHORT_MIN_VOTES", cohort_cfg.get("min_votes", 25))),
        m_value=int(os.getenv("COHORT_M_VALUE", cohort_cfg.get("m_value", 50))),
    )

    task_queue_settings = TaskQueueSettings(
        broker_url=os.getenv("TASK_QUEUE_BROKER_URL", task_queue_cfg.get("broker_url", "redis://localhost:6379/0")),
        result_backend=os.getenv(
            "TASK_QUEUE_RESULT_BACKEND", task_queue_cfg.get("result_backend", "redis://localhost:6379/1")
        ),
        default_queue=os.getenv("TASK_QUEUE_DEFAULT_QUEUE", task_queue_cfg.get("default_queue", "default")),
        scrape_queue=os.getenv("TASK_QUEUE_SCRAPE_QUEUE", task_queue_cfg.get("scrape_queue", "scrape")),
        stats_queue=os.getenv("TASK_QUEUE_STATS_QUEUE", task_queue_cfg.get("stats_queue", "stats")),
        enrichment_queue=os.getenv(
            "TASK_QUEUE_ENRICHMENT_QUEUE", task_queue_cfg.get("enrichment_queue", "enrichment")
        ),
    )

    return Settings(
        database=db_settings,
        scraper=scraper_settings,
        rss=rss_settings,
        tmdb=tmdb_settings,
        cohort_defaults=cohort_settings,
        task_queue=task_queue_settings,
        raw=data,
    )


def bool_from_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return bool(default)
    return value.lower() in {"1", "true", "yes", "on"}
