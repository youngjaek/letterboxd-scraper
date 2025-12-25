# Personalized Letterboxd Scraper — Architecture Plan

## Project Goals
- Build reusable datasets for multiple “taste cohorts” (e.g., me + people I follow, a friend + their followers).
- Keep data fresh without rerunning six-hour full scrapes each time.
- Expose fast ranking queries and exports without hand-written SQL each run.

## High-Level Architecture
```
scrapers/
    full_profile_scraper.py   # historical crawl per user
    rss_watcher.py            # incremental updates per user
    follow_graph.py           # builds cohort membership
pipeline.py                   # orchestrates scrape/update/export jobs
db/
    schema.sql                # normalized schema + migrations
    refresh_materialized.sql  # aggregate maintenance
cli.py                        # Typer/Click CLI entry point
config/
    default.toml / .env       # DB + scraping settings
```

### Data Flow
1. **Cohort definition**: given a seed user and depth rules, the follow graph scraper populates `cohort_members`.
2. **Full scrape**: fetch every member’s ratings and insert/update the normalized `ratings` table.
3. **Incremental loop**: RSS watcher polls members’ feeds for new/updated ratings or diary entries and patches rows in `ratings`.
4. **Aggregation refresh**: scheduled job recalculates cohort-level stats and derived rankings (materialized views).
5. **Exports/UI**: CLI commands read aggregates to generate CSVs, dashboards, or API responses.

## Database Model (PostgreSQL or SQLite)

```
users (
    id SERIAL PRIMARY KEY,
    letterboxd_username TEXT UNIQUE NOT NULL,
    display_name TEXT,
    avatar_url TEXT,
    last_follow_refresh TIMESTAMP
)

films (
    id SERIAL PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    year INT,
    poster_url TEXT
)

ratings (
    user_id INT REFERENCES users(id),
    film_id INT REFERENCES films(id),
    rating NUMERIC(3,1) NOT NULL,
    rated_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT NOW(),
    diary_entry_url TEXT,
    PRIMARY KEY (user_id, film_id)
)

cohorts (
    id SERIAL PRIMARY KEY,
    label TEXT NOT NULL,
    seed_user_id INT REFERENCES users(id),
    definition JSONB                      -- rules (depth, include_self, filters)
)

cohort_members (
    cohort_id INT REFERENCES cohorts(id),
    user_id INT REFERENCES users(id),
    depth INT NOT NULL,                   -- distance from seed
    followed_at TIMESTAMP,
    PRIMARY KEY (cohort_id, user_id)
)

cohort_film_stats (materialized view)
    SELECT
        cm.cohort_id,
        r.film_id,
        COUNT(*) AS watchers,
        AVG(r.rating) AS avg_rating,
        SUM(r.rating) AS rating_sum,
        MIN(r.updated_at) AS first_rating_at,
        MAX(r.updated_at) AS last_rating_at
    FROM ratings r
    JOIN cohort_members cm ON cm.user_id = r.user_id
    GROUP BY 1,2;

film_rankings (
    cohort_id INT,
    strategy TEXT,                         -- e.g., 'bayesian', 'wilson', 'discovery'
    film_id INT,
    score NUMERIC,
    rank INT,
    computed_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (cohort_id, strategy, film_id)
)
```

> **Portability**: SQLite supports the same schema (replace `SERIAL` with `INTEGER PRIMARY KEY`). PostgreSQL remains preferable for concurrent jobs and JSONB.

## Incremental Scraping Design
1. **Full profile scraper**
   - Input: list of usernames (per cohort) + checkpoint state.
   - For each user: paginate `/films/rated/…` pages, persist ratings, and store `last_full_scrape_at`.
   - Supports `--resume-from user` via checkpoints table to survive crashes.

2. **RSS watcher**
   - Poll interval configurable per user/cohort.
   - Reads RSS feed (`https://letterboxd.com/<user>/rss/`) and parses entries (diary/watch/reviews).
   - Extract film slug + rating if present; if only diary entry exists, store watch event but leave rating NULL.
   - Upsert into `ratings` (update `rating`, `rated_at`, `updated_at`) and enqueue a lightweight HTML fetch if the feed references a “rating updated” event.

3. **Follow graph refresher**
   - Given cohort definition, crawl `/following` pages, diff against `cohort_members`, and insert/delete rows as needed.
   - Triggered before large scrapes or on a schedule (e.g., weekly).

4. **Scheduler**
   - Could be a simple cron invoking CLI commands or a queue (Celery/RQ).
   - Example cadence:
     - Nightly: `cli.py scrape incremental --cohort my_friends`
     - Weekly: `cli.py cohort refresh --cohort my_friends`
     - Monthly: `cli.py scrape full --cohort my_friends --resume`
   - Scheduler ensures RSS watcher keeps the DB fresh while full scrapes repair drift or capture fields RSS omits (e.g., unrated watches).

5. **Backoff & throttling**
   - Shared HTTP client with rate limiter (token bucket) to respect Letterboxd.
   - Retries with exponential backoff for transient failures; persistent errors recorded in a `scrape_failures` table for manual review.

6. **Checkpointing**
   - `scrape_runs` table tracks job metadata (type, cohort, started_at, finished_at, status, notes).
   - `user_scrape_state` table stores last-successful page/time to resume partial runs.

## Ranking Strategies
Each strategy can be materialized via SQL or computed in Python, then stored in `film_rankings`.

1. **Bayesian Weighted Average**
   ```
   score = (v/(v+m)) * R + (m/(v+m)) * C
   ```
   - `R`: cohort average rating for the film.
   - `v`: number of cohort watchers (from `cohort_film_stats.watchers`).
   - `C`: overall cohort mean rating.
   - `m`: minimum votes threshold (configurable per cohort).

2. **Wilson Lower Bound**
   - Convert ratings to “positive” vs. “negative” by threshold (e.g., ≥3.5 stars positive).
   - Compute Wilson score to down-rank films with low sample sizes while rewarding high consensus.

3. **Discovery Score**
   ```
   discovery = normalized_cohort_rating - normalized_global_rating
   ```
   - Requires a global dataset (could be scraped aggregates or approximated from Letterboxd public stats).
   - Highlights films your cohort champions relative to the wider community.

4. **Recency Bias**
   - Weight ratings by age (`exp(-(now - rated_at) / τ)`) to surface films actively discussed recently.

5. **Hybrid Score**
   - Combine normalized components: `score = z(avg_rating) + α * z(log_watchers) + β * recency`.
   - Coefficients configurable per cohort.

Implementation plan:
- Store strategy parameters in a JSONB column (e.g., `film_rankings.params`).
- Provide CLI command `rank compute --strategy bayesian --cohort my_friends`.
- Cache results in `film_rankings` with `computed_at` for auditing.

## CLI & Configuration Plan
- Use [Typer](https://typer.tiangolo.com/) for a structured CLI.
- Commands:
  - `cohort build --seed <user> --label <label> [--depth 1]`
  - `cohort refresh --cohort <id>`
  - `scrape full --cohort <id> [--resume]`
  - `scrape incremental --cohort <id>`
  - `rank compute --cohort <id> --strategy <name>`
  - `export csv --cohort <id> --strategy <name> --min-score <x> --output <file>`
- Global options: `--config config/default.toml`, `--db-url`, logging verbosity.
- Configuration precedence: CLI args > environment variables > config file defaults.
- Logging & metrics: structured logs (JSON/text) plus optional progress bars via `rich`.

## Configuration & Secrets
- `.env` or `config/default.toml` holds DB credentials, scraping concurrency, delays, default user-agent, and RSS polling intervals.
- CLI accepts overrides (`--db-url`, `--cohort`, `--strategy`) for flexibility.

## Next Steps
1. Finalize schema + create migrations.
2. Implement CLI skeleton (Typer) with commands: `cohort build`, `scrape full`, `scrape incremental`, `refresh stats`, `export`.
3. Flesh out incremental scraping (RSS + HTML fallback) and ranking strategies.
