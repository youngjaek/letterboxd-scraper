# Phase 3 Product Layer — Development Approach

This guide explains how a competent developer can take the repo from the current pipeline-focused state (phases 1–2) into the **Phase 3 “Product Layer (Private Alpha)”** described in `docs/product_roadmap.md`. It focuses on engineering steps, sequencing, and validation signals rather than implementation minutiae so new contributors can jump in with shared context.

## 1. Confirm Readiness & Inputs

Before writing product code, verify that the lower layers are healthy:

- Scraper + enrichment success metrics from Phase 1 hold for representative cohorts (freshness, coverage, duplicate-free ratings).
- Phase 2 automation jobs (`cohort refresh → scrape → enrich → stats → rank`) are runnable via a single command/cron entry and emit telemetry that can be surfaced in the UI.
- Schemas used by the UI (`cohort_film_stats`, `film_rankings`, `ranking_insights`, saved exports) are stable enough for public reads; add migrations if still shifting.
- Decide where the product layer lives in the repo (recommended: `apps/api` + `apps/web` folders that import shared code from `src/letterboxd_scraper`).

> **Kickoff status (current):** the manual Redis + Celery runner executes the full pipeline end-to-end, and recent cohort/film data already exists in Postgres. Automation polish can follow later; nothing blocks API/UI scaffolding.

## 2. Architecture Decisions & Skeleton

1. **Service layout:** add an API service (FastAPI/Flask) that imports ORM models + celery tasks. Co-locate a lightweight web frontend (Next.js/Vite) or start with server-rendered templates if faster.
2. **Config boundary:** formalize `.env`/settings objects with explicit sections for API auth, Redis cache, Celery broker, and Letterboxd/TMDB credentials (already present for scrapers).
3. **Routing contract:** draft OpenAPI spec for MVP endpoints (`/auth/session`, `/cohorts`, `/cohorts/{id}/runs`, `/cohorts/{id}/stats`, `/filters`, `/exports`). Use schema objects reused from SQLAlchemy models/DTOs.
4. **Permissions:** plan for per-user ownership (API keys or magic-link login). Add tables `users`, `api_tokens`, and `cohort_memberships` with migrations before feature coding begins.

## 3. Backend/API Implementation Steps

1. **Auth layer**
   - Implement passwordless email login or signed API keys using `itsdangerous`/JWT. Store hashed tokens and map them to Letterboxd usernames when possible.
   - Provide CLI to create tokens for internal testers.
2. **Cohort management**
   - CRUD endpoints for cohort definitions (lists of usernames, curated list URLs, followers, manual additions).
   - Persist user ↔ cohort ownership, schedule preferences (full vs delta cadence), and metadata (display name, tags).
3. **Job triggers + status**
   - Expose POST `/cohorts/{id}/sync` that enqueues Celery tasks and returns job IDs.
   - Create `/cohorts/{id}/runs` to stream job history from `scrape_runs` + `stats_runs` tables; include telemetry already produced in phase 2.
4. **Stats/read endpoints**
   - Implement filtered reads from `cohort_film_stats`, `film_rankings`, and `ranking_insights` with query params mirroring CLI flags (release_year, watchers, percentile buckets, divergence thresholds).
   - Introduce caching (Redis) keyed by `(cohort_id, filter_hash)` so repeated UI queries reuse computed snapshots.
5. **Saved filters + smart lists**
   - Add `saved_filters` table with serialized filter JSON and metadata (owner, cohort_id, description, shareable slug).
   - Endpoints to list/create/share saved filters. Later, reuse the same table for embeds.

> **API progress:** `/health`, `/cohorts`, `/cohorts/{id}`, and POST `/cohorts` now expose listings, detail payloads, and creation; next steps layer auth, sync triggers, and stats reads atop this foundation.

> **Frontend progress:** Next.js app now reads `NEXT_PUBLIC_API_BASE_URL`/`NEXT_PUBLIC_API_KEY`, lists cohorts via `GET /cohorts`, surfaces the first cohort’s top rankings (`/cohorts/{id}/rankings`), and can create new cohorts by POSTing to `/cohorts/` with the API key header (temporary private-alpha flow).

## 4. Frontend/Web Experience

1. **Tech choice:** start with a simple single-page app (React + Vite or Next.js). Use shared UI toolkit or Tailwind for speed.
2. **Views to ship in alpha:**
   - **Dashboard:** pick a cohort → show latest sync status, top films, divergences, likes-only picks.
   - **Filters drawer:** map UI controls (sliders, multiselect) directly to API params; display cached responses.
   - **Saved lists:** grid of saved filters with quick-share buttons (copy slug, download CSV).
   - **Run history:** timeline with statuses from Celery (pending/running/success/failed).
3. **State management:** use React Query/SWR for caching, hooking into API responses + invalidation when filters change or new sync completes.
4. **Polish:** include TMDB attribution footer, loading indicators tied to API latency SLO (<750 ms cached, <3 s uncached) to keep watch on backend perf.

## 5. Export & Sharing Flow

- Extend existing export service to accept saved filter IDs; reuse CSV schemas from CLI exports.
- Generate shareable short links (`/s/{slug}`) that render read-only views without editing rights; ensure tokens include cohort + filter references but never expose private Letterboxd usernames unless owners consent.
- Add rate limits + logging for export downloads to avoid abuse.

## 6. Packaging, Deployments & Ops

1. **Docker compose (primary runtime):** add services for `api`, `frontend`, `worker`, `scheduler`, `db`, and `redis`. Document `.env` variables and default credentials in `README`. This stack becomes both the local dev environment and the artifact we deploy to low-cost hosts.
2. **Budget-aware hosting plan:**
   - **Short term:** run the compose stack on GitHub Codespaces or a local machine during development; no infra cost.
   - **Private alpha:** deploy the same compose bundle to a single VPS using DigitalOcean’s $200 student credit or Azure’s $100 credit. Start with the smallest instance (1–2 vCPU, 2–4 GB RAM) plus managed Postgres if affordable; fall back to a containerized Postgres when credits are tight.
   - **Supporting services:** use the Pack’s Redis add-ons (e.g., Azure Cache, DO Managed Redis) only when needed; otherwise rely on the compose-provided Redis. GitHub Pages + a free `.me`/`.tech` domain cover the marketing site.
   - **Future scale:** capture infra-as-code (Terraform) early so graduating to AWS/GCP or Kubernetes later is a lift-and-shift instead of a rewrite, but do **not** introduce Kubernetes/EKS until the hosted alpha outgrows a single VM. Scaling focus remains on application efficiency: profile slow SQL queries, add Redis caches, batch Celery jobs, and keep API responses lean. A single well-tuned VM serving multiple containers via an NGINX/Traefik reverse proxy easily handles hundreds of concurrent requests; the limiting factor will be DB I/O and scraper throughput, not orchestration tech.
3. **Environment promotion:** define `dev`, `staging`, `alpha` config files; guard production-only secrets. Use the same compose stack for self-hosted testers so setup matches the hosted environment.
4. **CI updates:**
   - Lint/test API + frontend along with Python code.
   - Add integration tests that spin up a throwaway DB, seed fixture cohorts, and hit API endpoints (can run inside GitHub Actions with service containers).
5. **Observability:** export structured logs, Prometheus metrics, and uptime probes. Surface them in the UI admin area for transparency; when moving to cloud credits, pair the VM with lightweight monitoring (Grafana Cloud free tier or Azure Monitor).

> Hosting summary: Phase 3 deliberately avoids Kubernetes/AWS managed fleets; Docker Compose + student cloud credits keep operational costs near zero while still demonstrating production-like deployment skills. Treat performance work as a product concern—optimize DB indexes, precompute stats, and keep Celery queues draining—so vertical headroom on a single VPS lasts longer. Document the migration path to more robust infra (Terraform modules aiming at ECS/Kubernetes) but defer until real workloads demand it.

## 7. Verification & Exit Criteria

To graduate Phase 3, validate:

- ≥5 invite-only testers can create cohorts, run syncs, and view stats without CLI access.
- UI/API error rate <2% over rolling week; retries auto-trigger when scraper jobs fail.
- Saved filters load from cache in <1 s at p95; cold queries still under 3 s.
- CSV exports + share links include attribution and respect user-level permissions.
- Docker compose install steps verified on clean machine (documented in `docs/workflow.md`).

## 8. Risks & Mitigations

- **Schema churn:** keep API response DTOs decoupled from raw SQLAlchemy models to avoid breaking clients when tables change; version endpoints if needed.
- **Rate limits / scraping ethics:** UI-triggered syncs must respect the scheduler throttling. Enforce quotas per user and queue jobs rather than immediate scrapes.
- **Security:** store API keys hashed, log auth events, and build a revocation path before inviting testers.
- **Support load:** add admin-only endpoints/pages to inspect cohorts, rerun jobs, and view telemetry so issues can be triaged quickly.

Document progress in this file as milestones complete so future contributors know what remains for the Phase 3 alpha.
