# Letterboxd Cohort Analyzer — Vision & Roadmap

This document captures the current vision, architectural direction, and phased roadmap for turning the existing Letterboxd cohort scraper into a product that cinephiles (not just CLI users) can rely on. It summarizes the motivation, required scraping/enrichment work, data model changes, and the product layer we plan to build on top.

## Motivation Recap

- Letterboxd has ~20M members, so global averages or “popular with friends” sorting do not reflect niche circles or closely aligned friend groups.
- Users often align with a specific cohort (friends, critics, curated lists) and want rankings such as “top 2010s films among my circle,” “biggest disagreements with global Letterboxd,” “PTA ranked by my circle,” etc.
- Letterboxd only exposes per-film friends’ averages and a slow, opaque “popularity with friends” sort. No API exists for deeper cohort analytics.
- Our scraper already builds cohorts, fetches ratings, and computes rankings; the next step is packaging this data as a usable product.

## High-Level Vision

Deliver a “Cohort Almanac” experience where any Letterboxd user can:

1. Define a cohort (followers, critics, list members) without touching CLI commands.
2. Keep that cohort’s ratings/likes synchronized via full scrapes plus incremental rated-date deltas that stop once the scraped `(user_id, film_id, rating)` triple already exists in the DB.
3. Explore ready-made insights: top-ranked films, hidden gems, divergence from global averages, favourites/likes, temporal slices, director/genre filters, etc.
4. Share or export curated lists (CSV, shareable links, Letterboxd list templates) powered by their trusted circle instead of the global crowd.

Scraping remains an internal implementation detail; end users interact with a UI/API backed by our database.

## Success Metrics & Release Bar

We graduate each phase only when the platform meets these measurable targets:

- **Data completeness:** ≥99% of tiles per scrape include rating, like/favourite flags, and TMDB IDs (remaining outliers land in a tracked “needs enrichment” queue).
- **Freshness:** Full-cohort rebuild (≤100 members, 30–40k films) completes within 30 minutes end-to-end; incremental rated-date scrapes persist to the DB within 5 minutes for 95% of deltas.
- **Data integrity:** Zero duplicate `(user_id, film_id)` rows post-run; histogram totals reconcile with ratings within ±1% or the pipeline fails fast.
- **Pipeline reliability:** Scrape → enrichment → stats workflow succeeds ≥98% over a rolling 7-day window with automatic retries capped at 3 per job.
- **API latency:** Cached cohort-stats endpoints return <750 ms at p95, uncached heavy queries <3 s at p95 while serving ≥10 concurrent cohorts.
- **Test & tooling:** Regression tests cover scraper parsing, rated-date delta handling, TMDB enrichment, and stats aggregation; CI gates merges on these suites.
- **Compliance:** All outbound fetches identify our polite user agent, respect Letterboxd/TMDB rate limits, and emit the attribution copy before any UI/export release.

## Collaboration & Learning Notes

- Primary contributor is ramping up on backend topics (throughput, async workers, persistence, caching, security). Roadmap discussions and implementation plans should include rationale and learning resources so each step doubles as mentorship.
- Keep this document in sync with what’s been learned: annotate tricky concepts (queues, migrations, observability) and link to follow-up guides so future sessions start with the same context.
- Leave the roadmap uncommitted while it’s evolving; we’ll promote it into the repo once the plan stabilizes.

## Data Sources & Scraping Enhancements

| Source | Purpose | Notes |
| --- | --- | --- |
| `/user/films/rated/.5-5/page/{n}/` + `/by/rated-date/` | Ratings + likes per user | Extend current scraper to capture liked/favourited state per tile (classes like `icon-liked`, `poster-liked`). Incremental runs hit the `by/rated-date` sort (newest rating first), update a row if the rating changed, and halt when `(user_id, film_id, rating)` already matches the DB. |
| `/user/likes/films/rated/none/` | Films that were liked but not rated | Uses the same poster grid; store `rating=NULL`, `liked=TRUE`. Default sort (“when liked”) already surfaces newest likes first, so incremental runs can stop once the DB matches while occasional full sweeps catch rare like removals/re-adds. |
| `/film/{slug}/` page | Film metadata, TMDB ID, internal film ID | `<body data-tmdb-id="1018">` exposes TMDB linkage; poster modal includes `data-film-id`, `data-details-endpoint`. |
| `/film/{slug}/json/` | Structured film metadata | JSON payload powering poster modal; includes rating summaries, like counts, release info. |
| `/csi/film/{slug}/ratings-summary/` | Rating histogram (½-star buckets) | Needed for cohort-level distribution comparisons. |
| TMDB API (`movie/{id}`, `movie/{id}/credits`) | Posters, genres, runtimes, release dates, crew/directors | Use slug→TMDB ID mapping from the film page to enrich `films`; pull credits to extract `job == "Director"` entries. |

### Scraper Improvements

- **Metadata persistence:** Update `services.ratings.get_or_create_film` to store title, release year, TMDB ID, poster URL, runtime, directors, and other TMDB-derived fields. Add a background job that enriches any newly seen slug.
- **Incremental rated-date ingest:** When scraping `/by/rated-date/`, walk tiles newest-to-oldest, upsert if the rating changed, and halt once the scraped `(user_id, film_id, rating)` triple already matches what’s stored. Persist the latest `liked/favorite` flags during the same pass so the DB stays aligned with re-rates that bubble to the top.
- **Likes/favourites:** Add `liked` and `favorite` boolean columns to `ratings` (or a separate `user_reactions` table) so per-film like counts and favourite percentages can be aggregated.
- **Rating distributions:** When scraping `/film/{slug}/json/` or the CSI histogram, persist counts per rating bucket per cohort (could be a JSON field or a dedicated `film_histograms` table). This differentiates films with the same average but different consensus profiles.
- **Throttling & compliance:** Maintain the `ThrottledClient`, add jitter/backoff, and document polite crawling best practices (delay, user-agent, cap on frequency) to avoid stressing Letterboxd.
- **Parallelization:** Move scraping into a queue + worker pool (Celery/RQ/APS) so user pages, film pages, and TMDB enrichment can run concurrently while still honoring per-domain rate caps.
- **Response caching:** Cache TMDB payloads (Redis or sqlite-backed cache) with TTL + ETag handling and reuse parsed Letterboxd film JSON to minimize duplicate downloads.

## Data Model Updates (Relational)

Additions/changes on top of `db/schema.sql`:

- `films`: add `tmdb_id`, `imdb_id`, `poster_url`, `runtime_minutes`, `primary_director`, `genres` (array/json).
- `ratings`: add `liked BOOLEAN`, `favorite BOOLEAN`, `rating_distribution JSONB` (or keep distribution in aggregated tables), `diary_entry_url` (exists), `rated_at`.
- `film_histograms` (new): `(film_id, global_bucket_counts JSONB, cohort_bucket_counts JSONB)` or a normalized `(film_id, bucket_label, count)` table keyed per cohort.
- `film_metadata_sync`: optional table to track enrichment status (pending, fetched, failed) for each slug/TMDB ID.
- `tmdb_payloads` (optional): persist TMDB JSON per `tmdb_id` so we can rehydrate genres/countries/directors offline and avoid blowing through rate limits.

Materialized view `cohort_film_stats` will be extended to include:

- `liked_count`, `favorite_count`.
- Percentages (`liked_pct`, `favorite_pct`).
- Divergence metrics (`avg_rating_delta` vs global).
- Histogram fingerprints (tight consensus, bimodal, “all likes no ratings”) derived from stored bucket distributions.

`ranking_insights` already stores percentiles/z-scores; extend its computation to incorporate like/favourite percentages and rating-distribution tags (e.g., “bimodal,” “tight consensus”).

## Migration & Backfill Strategy

- Snapshot the current ~200-user dataset for regression testing, then treat the upcoming schema as a clean break (drop/recreate tables).
- Provide a `bootstrap_full_cohort` command that truncates derived tables, re-seeds cohorts, runs full scrapes, enriches films, and backfills histograms so we can redeploy or migrate anytime.
- Version fixtures for rated-date poster grids, likes pages, and TMDB payloads so automated tests stay deterministic even as the production database is rebuilt.
- Once the schema stabilizes, reuse the same command for controlled reprocessing (e.g., new histogram logic) instead of ad-hoc SQL migrations.

## Application Architecture

```
                         ┌──────────────────────────┐
                         │  Web / API Frontend      │
                         │  (cohort setup + UI)     │
                         └────────────┬─────────────┘
                                      │ REST/GraphQL
       ┌────────────────────────┐     │
       │ Scheduler / Workers    │◄────┘
       │ (Celery/RQ/APS)        │
       └──────────┬─────────────┘
                  │ enqueued jobs
        ┌─────────▼─────────┐
        │ Scraper Services  │
        │  - Follow graph   │
        │  - Ratings/likes  │
        │  - Film metadata  │
        │  - Incremental    │
        │    rated-date     │
        │    updates        │
        └─────────┬─────────┘
                  │ SQLAlchemy
        ┌─────────▼─────────┐
        │ Postgres          │
        │  users, films,    │
        │  ratings, cohorts │
        │  film_rankings    │
        │  ranking_insights │
        └─────────┬─────────┘
                  │
        ┌─────────▼─────────┐
        │ Analytics Layer   │
        │  - cohort stats   │
        │  - ranking/bucket │
        │  - histogram data │
        └────────────────────┘
```

Key ideas:

- The existing CLI workflows become job handlers invoked by the scheduler or API triggers. Each handler reuses current services (`cohort refresh`, `scrape full/incremental`, `stats refresh`, `rank compute`, `rank buckets`).
- A metadata enrichment worker runs after scrapes to fetch TMDB data and rating histograms for any new films.
- The web/API layer reads from `film_rankings`, `ranking_insights`, and `cohort_film_stats` to render dashboards (top films, hidden gems, divergences, filters).
- Provide a self-hosted bundle (Docker compose) for power users plus a hosted multi-tenant deployment for the general audience.

## Filtering & Insights

Filters to expose in the UI (powered by stored data):

- **Rating band:** avg rating range, Bayesian score range, percentile thresholds.
- **Watchers:** min/max watchers, percentile, log-scaled buckets.
- **Likes/favourites:** min liked count, favourite percentage.
- **Divergence:** difference between cohort avg and global Letterboxd avg.
- **Temporal:** release year range, watched-year, recent N years (already supported in `rank buckets`).
- **People:** director, actor, writer (via TMDB), cohort membership presence (e.g., “rated by ≥X critics”).
- **Distribution shape:** classification based on histogram (e.g., high variance vs tight consensus).
- **Taste alignment:** similarity scores between users (e.g., cosine similarity over shared ratings, percentage of matching star buckets) enabling follow recommendations or “users most aligned with you.”
- **Social graph overlap:** mutual-follow counts or shared cohort membership to surface critics/friends you should follow.

Prebuilt slices:

- “Elite acclaim” (top percentile rating + watchers).
- “Cult favorite” (high rating, low watchers).
- “Divisive vs Letterboxd.”
- “Most liked, unrated” (likes-only entries).
- “Top PTA films among your circle,” etc.

## Roadmap (Phased)

### Phase 1 — Core Stabilization

1. Harden current CLI workflows; ensure `letterscraper` hits the success metrics (completeness, freshness, duplication) on representative cohorts.
2. Extend rating scrapers to capture likes/favourites and persist them alongside ratings.
3. Introduce film metadata enrichment (TMDB ID, poster, runtime, directors) with cached TMDB calls and retries.
4. Persist rating histograms via `/json/` + `/csi/` endpoints and derive consensus tags.
5. Simplify or retire legacy scraper helpers that TMDB replaces (e.g., poster parsing) and remove the existing “smart bucket” implementation if the new filter system supersedes it.
6. Expand automated tests (unit + integration with fixtures).
7. Exit criteria: <30 min cohort rebuild, ≥99% TMDB coverage, rated-date delta tests green, and zero duplicate `(user_id, film_id)` rows in `ratings`.

### Phase 2 — Pipeline Automation

1. Build a job runner (Celery/RQ/APS) that chains existing CLI steps:
   - `cohort refresh` → `scrape full` (or incremental) → `stats refresh` → `rank compute` → `rank buckets`.
2. Implement telemetry/monitoring using `services.telemetry` outputs; add dashboards/log shipping plus SLO alerts on latency/failure rate.
3. Schedule rated-date incremental updates plus periodic metadata enrichment with worker pools respecting tuned concurrency caps.
4. Add admin tooling to inspect scrape runs, cohort health, and film sync status; expose replay/backfill buttons per cohort.
5. Introduce shared caches (Redis/memcached) so frequent stats queries reuse precomputed cohort snapshots instead of recomputing on every request.

### Phase 3 — Product Layer (Private Alpha)

1. Create a minimal web/API frontend that lets users:
   - Authenticate (API key or passwordless email) and define/save cohorts (followers, curated lists, critic mixes).
   - Trigger syncs (enqueue jobs) and view run status.
   - Explore ranking tables, divergences, favourites, and bucket insights.
2. Persist saved filters/smart lists per user so multiple people can query the same `cohort_film_stats` cache concurrently without recomputation.
3. Bundle CSV exports and shareable list links using existing export service with TMDB + Letterboxd attribution baked in.
4. Provide Docker compose for self-hosting; run a hosted instance for a small invite-only group.

### Phase 4 — Scale & UX Polish

1. Add richer visualizations (rating histograms, scatter plots of watchers vs avg rating) leveraging `ranking_insights`.
2. Implement saved filters/smart lists (persisted timeframe keys).
3. Introduce notifications/digests (“new films your cohort loves”) and social features (taste similarity leaderboards, follow suggestions).
4. Optimize scraping throughput with sharded worker pools and adaptive throttling.
5. Formalize onboarding, billing (if needed), and documentation (ethics, rate limits, FAQ).

## Compliance & Ethics

- Confirm `/robots.txt` coverage for each path we touch and codify throttling delays + user agent strings in config.
- Attribute TMDB in UI/exports and keep a policy page describing data sources, contact info, and takedown process before inviting private-alpha users.
- Log outbound request volumes and build alerting for unusual spikes to catch bugs that could unintentionally hammer Letterboxd/TMDB.
- Document a response plan (pause scrapes, notify users) in case Letterboxd requests changes or if privacy complaints emerge.

## Repo Strategy

Keep the scraper, data model, and service code in the existing repository to preserve shared logic (`src/letterboxd_scraper/…`). Build the web/UI layer either:

- as a sibling package within the same monorepo (e.g., `apps/web` or `services/api`) to share models/configs directly, or
- in a separate repo if the stack diverges significantly (e.g., React frontend). In that case, publish the scraper as a Python package so the backend can depend on it.

For now, favor a monorepo: it keeps scraper, scheduler, API, and docs together, simplifies cross-component changes, and avoids version skew while the product is rapidly evolving. Once the API/UI stabilizes, we can revisit splitting if necessary.

## Open Questions

- Final schema for rating distributions (JSON vs normalized table).
- Whether to store TMDB payloads verbatim for offline use or only selected fields.
- Auth model for the hosted product (Letterboxd OAuth is unavailable; may need passwordless + manual username entry).
- Licensing/compliance considerations when hosting scraped data—needs review before public beta.
- Scope of scraper refactors/removals (poster metadata helpers, smart buckets) vs. reuse; revisit once TMDB enrichment and new filtering features are defined.

This document should be updated as the architecture and roadmap evolve. Use it as the canonical reference when implementing features or onboarding collaborators.
