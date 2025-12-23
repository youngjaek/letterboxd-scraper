# letterboxd-ratings-scraper

Personalized Letterboxd cohort scraper that builds per-friend-group rankings by:
- Crawling follow graphs to define “cohorts” (you + people you follow, Filipe + their follows, etc.).
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
    workflow.md            # CLI workflow cheat sheet
db/schema.sql              # Normalized schema + materialized view
tests/                     # Mock-based scraper tests
```

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
   ```

4. **Run tests**
   ```bash
   pytest
   ```
