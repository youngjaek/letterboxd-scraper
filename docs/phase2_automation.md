# Phase 1 → Phase 2 System Design Notes

These notes capture how I’m approaching the current Letterboxd cohort project as a production-ready system. They summarize the design decisions already made in Phase 1 (data ingress + modeling) and spell out the rationale for Phase 2 (automated pipelines, orchestration, and observability). The goal is to make every trade-off explicit so you can revisit the reasoning later or map it to future phases.

---

## 1. Phase 1 Lessons & Design Choices

### 1.1 Data Modeling
- **Normalized core tables**: `users`, `films`, `ratings`, `cohort_members`, `cohort_film_stats`, `film_rankings`, `film_people`, `film_histograms`, `ranking_insights`. Each entity has a narrow responsibility so ingest/aggregation jobs can be incremental:
  - `ratings` keeps the raw events `(user_id, film_id, rating, liked, favorite, updated_at, rated_at)`.
  - `cohort_film_stats` pre-aggregates watchers/averages/first+last rating timestamps per cohort.
  - `film_rankings` materializes scoring strategies (Bayesian, engagement-enhanced, consensus) to avoid recomputing on every query.
  - `film_histograms` stores the per-film bucket counts scraped from `/json`/`/csi` so distribution-aware stats can run offline.
  - `ranking_insights` caches derived labels (consensus/divergence/smart buckets).
- **Why normalized first?** Scrapes are append-heavy and can retrace users, so deduping `(user_id, film_id)` at the ratings layer keeps the state canonical. Downstream tables get refreshed deterministically from the canonical events, reducing the risk of drift and making retries idempotent.
- **Indexes & partitions**: Composite indexes on `(cohort_id, film_id)`, `(film_id, cohort_id)`, `(user_id, film_id)`, `(ratings.updated_at)`, plus partial indexes for “recent” filters keep incremental jobs fast. Partitioning `ratings` by cohort or by user is planned once row counts demand it; for now the indexes + `updated_at` filters meet the <30 min cohort rebuild target.

### 1.2 Scraping & Enrichment
- **Incremental-by-default**: Scrapers hit rated-date sorted pages and stop when the `(user_id, film_id, rating)` tuple already exists, so incremental runs stay proportional to actual changes. Full rebuilds only happen on cohort creation or manual backfills.
- **Likes/Favorites capture**: Poster tiles expose CSS classes for liked/favorited states; capturing them during the same pass means we avoid an extra request per film and can compute engagement-derived scores.
- **Metadata enrichment**: Film detail scrapes fetch TMDB IDs, runtime, director/actor info, histogram endpoints. Responses are cached locally and reused for multiple cohorts referencing the same film. Missing metadata is queued for enrichment workers after each scrape to prevent blocking the ingest flow.
- **Data quality guardrails**: Each scraper/enrichment step writes telemetry rows (`scrape_runs`, `enrichment_runs`) that log counts, durations, and error samples. Automated tests verify parser correctness and duplicate-prevention logic before merges.

### 1.3 Performance & Reliability Patterns
- **Bayesian + engagement scoring**: Storing multiple scoring strategies in `film_rankings` lets the UI/API read precomputed rows with a simple indexed query. We compute Bayesian mean, likes/favorites z-scores, and histogram-derived consensus bonuses in one pass so downstream surfaces are simply filtered projections.
- **Advanced search readiness**: Histograms + per-film derived stats (std_dev, skewness, high_rating_pct) are materialized so the later “Advanced search” feature can run purely out of Postgres with WHERE clauses instead of recomputing heavy aggregates.
- **Caching plan**: Although Phase 1 didn’t ship Redis yet, the data model is structured so caches can safely invalidate via `cohort_id` + `strategy` + `params_hash`. This is the foundation for Phase 2 warmers.
- **Testing & fixtures**: Fixtures cover scraper parsing, rated-date stop conditions, dedupe logic, TMDB enrichment fallbacks, and stats aggregation. Integration tests load sample cohorts into SQLite/Postgres and run the pipeline to assert row counts + histogram totals. This ensures Phase 2 automation has trustworthy building blocks.

---

## 2. Phase 2 Automation Blueprint

Phase 2 moves from “manual CLI orchestration” to “continuous, observable data service.” The design leans on proven backend patterns to hit the roadmap targets (freshness, reliability, cacheability).

### 2.1 Task Orchestration & Queues
- **Task runner**: Celery (Python-native) backed by Redis. Reasons:
  - Native chaining/retries/rate limiting are essential once multiple cohorts/users run simultaneously.
  - The stack stays homogeneous (Python) so we can call the existing service functions directly instead of shelling out.
  - Celery Beat (or APScheduler) gives clustered cron-like scheduling without relying on OS-level cron jobs.
- **Task graph**: For each cohort build:  
  `cohort_refresh → scrape_incremental → stats_refresh → rank_compute → rank_buckets → enrich_missing → cache_warm`.  
  Celery Canvas chains encode the dependency graph, and `link_error` callbacks notify ops when a stage fails.
- **Queues & concurrency**: Separate queues for `scrape`, `enrich`, `stats`, `cache`. Concurrency caps ensure we respect Letterboxd/TMDB rate limits (e.g., 2 concurrent scrapes, 5 concurrent enrichment workers). Celery task annotations enforce rate limits per queue.
- **Idempotency & dedupe**: Every task logs to a `job_runs` table keyed by `(task_name, args_hash)`. Before performing work, a task checks recent entries to avoid duplicate runs. Intermediate checkpoints (e.g., “last processed user/page”) let retries resume mid-batch.

### 2.2 Scheduling Strategy
- **Event-triggered**: Creating a cohort enqueues the full chain automatically. Operators can kick off ad-hoc rebuilds via CLI/admin UI (which just enqueue the same tasks).
- **Daily incremental**: Scheduler iterates users in batches (1k per task) and enqueues `incremental_user_scrape(user_ids)` tasks. Each batch dedupes film IDs and triggers enrichment for any new titles. This keeps everyone’s ratings fresh within 24 hours.
- **Weekly/monthly full enrichment**: A dedicated job iterates every unique film in the database (or per cohort) to refresh TMDB metadata and histograms. This catches stale posters/runtime/credit changes even when no recent ratings touched the film.
- **No scheduled full ratings scrape**: Full scrapes only run when a cohort is rebuilt or data integrity checks fails. Incremental rated-date runs are enough for freshness; this reduces Letterboxd load and shortens recovery time.

### 2.3 Caching & Derived Data
- **Redis namespaces**:
  - `cohort:{id}:strategy:{name}:slice:{params_hash}` → cached ranking/query responses for advanced filters.
  - `film:{id}:metadata` → TMDB payload cache, expiring after the monthly sweep.
  - `job:{id}` → job progress snapshots exposed in the admin UI.
- **Warmers**: After stats/rank jobs, enqueue cache warmers for popular slices: default top N, “high watchers,” “recent release year buckets,” divergence lists. This keeps API latency <750 ms as required.
- **Materialized views refresh**: Postgres refresh commands (or stored procedures) run as part of the pipeline so the DB-side caches (`cohort_film_stats`, `film_rankings`, `ranking_insights`) stay synchronized with Redis.

### 2.4 Telemetry & Observability
- **Metrics**: Each task emits structured metrics (duration, rows processed, API calls, failures) via OpenTelemetry exporters to Prometheus/Grafana (or any preferred stack). Key SLIs: incremental scrape p95 latency, cohort rebuild duration, enrichment queue depth, cache hit rate.
- **Structured logging**: JSON logs with job IDs/task names keyed to `job_runs` rows aid debugging and make it easy to build “slow job” dashboards.
- **Alerts**: Threshold-based alerts for failure rate spikes (>2 failures in 10 min), stale cohorts (no successful pipeline in 24 h), enrichment backlog growth, TMDB rate-limit responses. Alerts integrate with chat/on-call tooling.

### 2.5 Operational Tooling
- **Admin UI/CLI**: FastAPI module (or CLI command) listing:
  - Scheduled jobs + next run time.
  - In-progress tasks, durations, args.
  - Recent failures with stack traces and retry buttons.
  - Per-cohort freshness (time since last successful stats refresh).
- **Replay & resume**: Operators can enqueue `resume_job(job_id)` tasks, which consult checkpoints to pick up where they left off.
- **Secrets & config**: Environment-driven config for Celery broker URL, TMDB/API keys, concurrency caps. Shared settings are centralized so workers, admin UI, and CLI stay consistent.

### 2.6 Testing & Validation
- **Unit tests**: Cover task wiring (ensure the chain is built correctly), job dedupe logic, checkpoint persistence, cache key computation, and error handling.
- **Integration tests**: Spin up Redis/Postgres locally (via docker-compose or testcontainers), run the end-to-end pipeline on a fixture cohort, and assert final table counts + cache warmers. This ensures automation behaves the same way as manual Phase 1 runs.
- **Load testing**: Simulate multiple cohorts/users to validate concurrency settings, queue throughput, and database contention before production use.

---

## 3. Why These Choices Work for Scalability & Maintainability

| Concern | Approach | Rationale |
| --- | --- | --- |
| **Scalability** | Task queues + Redis caching + materialized tables. | Work can be horizontally scaled by adding workers; caching keeps hot queries off the DB; materialized tables avoid expensive runtime joins. |
| **Reliability** | Idempotent tasks + retries + observability. | Failures can be retried safely, telemetry surfaces regressions quickly, and checkpointing prevents data duplication. |
| **Maintainability** | Reuse Python service layer, structured job metadata, admin UI. | Tasks stay thin wrappers around existing functions, instrumentation is centralized, and operations can inspect/trigger work without ad-hoc scripts. |
| **Performance** | Indexed normalized schema + cache warmers + rate limits. | DB remains query-friendly even as data grows, and caching ensures API latency targets are met without overloading Postgres. |
| **Future product surfaces** | Precomputed histograms, divergence stats, consensus labels. | Phase 3 features (advanced filters, personalized predictions) are already backed by data stored in Phase 1/2, so product work can focus on UX/API. |

---

## 4. Next Steps Checklist

1. Implement Celery/Redis infrastructure (broker config, worker deployment, Beat scheduler).
2. Wrap existing CLI workflows into callable Python services; expose them as Celery tasks with structured logging.
3. Create `job_runs`/`job_events` tables and helper utilities for checkpoints + dedupe.
4. Define scheduling rules (event-triggered, daily user batches, weekly/monthly full enrichment) in Beat/APScheduler.
5. Add cache layer (Redis client, invalidation helpers, warmers).
6. Build the admin CLI/UI and dashboards for telemetry.
7. Load-test the orchestrated pipeline on representative cohorts; adjust concurrency limits and indexes as needed.

With these pieces in place, Phase 2 will deliver the “pipeline automation” milestone outlined in `docs/product_roadmap.md`, giving the data products described in `docs/data_products.md` a dependable foundation.
