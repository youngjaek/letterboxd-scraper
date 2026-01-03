# letterboxd-ratings-scraper

Personalized Letterboxd cohort scraper that builds per-friend-group rankings by:
- Crawling follow graphs to define “cohorts” (you + people you follow, a friend + their follows, etc.).
- Scraping each member’s rated films, storing normalized ratings, and refreshing stats.
- Computing ranking strategies (currently Bayesian weighted average) and exporting CSV lists.
- Applying incremental updates via each member’s Letterboxd RSS feed so data stays fresh.

## Project Structure

```
src/letterboxd_scraper/
    cli.py                 # Typer-based CLI entry point
    config.py              # TOML + env configuration loader
    db/                    # SQLAlchemy models + session helpers
    scrapers/              # Follow graph, ratings, RSS scrapers with throttled HTTP client
    services/              # Cohort, rating, ranking, export, RSS update logic
docs/
    architecture_plan.md   # Detailed system design
    ranking_architecture.md # Ranking + smart bucket data flow
    workflow.md            # CLI workflow cheat sheet
db/schema.sql              # Normalized schema + materialized view
tests/                     # Mock-based scraper tests
```

## CLI Usage

The Typer CLI surfaces each workflow step. Commands are grouped by workflow so you can find the exact invocation you need.

### Cohort commands

- `letterboxd-scraper cohort build --seed <username> --label "<label>" [--depth N] [--include-seed/--no-include-seed]` — create a cohort definition and seed membership.
- `letterboxd-scraper cohort list` — print existing cohorts with IDs, labels, seeds, and member counts.
- `letterboxd-scraper cohort refresh <cohort_id>` — re-crawl the follow graph to sync members with the configured depth.
- `letterboxd-scraper cohort rename <cohort_id> --label "<new label>"` — update a cohort's display label.
- `letterboxd-scraper cohort delete <cohort_id> [--yes]` — remove a cohort and its associated members/rankings (prompts for confirmation).

### Scraping + stats commands

- `letterboxd-scraper scrape full <cohort_id> [--resume]` — run a historical scrape for every cohort member.
- `letterboxd-scraper scrape incremental <cohort_id>` — apply RSS-driven updates across the cohort.
- `letterboxd-scraper stats refresh [--concurrent/--no-concurrent]` — rebuild the `cohort_film_stats` materialized view.

### Ranking + export commands

- `letterboxd-scraper rank compute <cohort_id> [--strategy bayesian]` — compute `film_rankings` entries.
- `letterboxd-scraper rank subset <cohort_id> (--list-path user/list/some-list/ | --filmography-path/--filmo-path actor/sample-performer/ | --html-file path) [--limit N]` — filter an existing ranking set against a Letterboxd list, filmography page, or saved HTML.
- `letterboxd-scraper rank buckets <cohort_id> [--strategy bayesian] [--release-start YEAR] [--recent-years N] [--persist] [--load timeframe-key]` — compute percentile buckets + engagement clusters, optionally constrained by release year or when the cohort logged the films, and persist the derived “smart list” definitions.
- `letterboxd-scraper export csv <cohort_id> [--strategy bayesian] [--min-score N] --output exported/my_friends.csv` — write ranking results to CSV.

Each command respects configuration passed via `.env`, environment variables, or TOML config files (see below).

#### Smart ranking buckets

`rank buckets` analyzes the existing `cohort_film_stats` view to automatically surface interesting clusters without hand-tuning thresholds:
- Percentile buckets adapt to the cohort distribution (e.g., “Elite acclaim,” “Cult favorite,” “Crowd pleaser”).
- Cluster labels rely on z-scores for watchers vs. average rating to highlight “High rating / low watchers,” “High engagement / mixed sentiment,” etc.
- Temporal filters (release window, specific watch year, `--recent-years` rolling window, or explicit `--watched-since/--watched-until`) let you focus on “this year,” “last 5 years,” or any bespoke slice.
- Use `--persist` to cache the current computation, then `--load <timeframe-key>` to rehydrate those smart lists in exports or dashboards without recomputing.

## Getting Started

1. **Install dependencies**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

2. **Configure database & environment**
   - Copy `.env.example` to `.env`, set `DATABASE_URL`.
   - Apply schema (`psql -f db/schema.sql` or migration tool).

3. **Run CLI workflow**
   ```bash
   letterboxd-scraper cohort build --seed my_username --label "My Friends"
   letterboxd-scraper cohort refresh 1
   letterboxd-scraper scrape full 1
   letterboxd-scraper stats refresh
   letterboxd-scraper rank compute 1 --strategy bayesian
   letterboxd-scraper export csv 1 --strategy bayesian --output exported/my_friends.csv
   ```
   For subsequent updates:
   ```bash
   letterboxd-scraper scrape incremental 1
   letterboxd-scraper stats refresh
   letterboxd-scraper rank compute 1 --strategy bayesian
   letterboxd-scraper rank subset 1 --strategy bayesian --list-path user/list/example-list/
   ```

4. **Run tests**
   ```bash
   pytest
   ```
