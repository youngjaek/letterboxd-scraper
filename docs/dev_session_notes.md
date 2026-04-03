# Dev Session Notes — Phase 3 UI/API

_Last updated: $(date -u +"%Y-%m-%d %H:%M:%SZ")_

## Where we left off
- FastAPI exposes cohort CRUD, rankings, and sync endpoints. Auth uses `X-API-Key`.
- Next.js app lists cohorts, shows per-cohort rankings, and provides create/rename/delete/sync actions.
- Docker Desktop + `docker-compose.dev.yml` now spin up Redis and the Celery worker; the worker connects to Postgres via `DATABASE_URL` defined in `.env.docker`.
- A running stack currently consists of:
  1. Docker Desktop running.
  2. `docker compose -f docker-compose.dev.yml up redis celery-worker` running in its own terminal.
  3. API (`uvicorn apps.api.main:app --reload`).
  4. Frontend (`cd apps/web && npm run dev`).

## Next steps / TODOs
- Implement the Cohort Affinity scoring strategy end to end (materialized stats, `cohort_affinity` rank computation, API surface).
- Flesh out cohort detail page with richer stats (filters, strategy dropdown) using `/cohorts/{id}/rankings` and upcoming stats endpoints.
- Add job status visibility: surface Celery job IDs and their progress/logs in the UI.
- Implement API key management helpers (CLI command or API endpoint) so testers can mint/revoke keys without DB writes.
- Wire Docker Compose into documentation/Makefile for ease of use; consider containerizing Postgres for full isolation.

## Daily startup checklist
1. **Launch Docker Desktop** (skip if already running).
2. **Start Redis + worker**
   ```bash
   docker compose -f docker-compose.dev.yml up --build redis celery-worker
   ```
   Leave this terminal open.
3. **Start API** in a new Git Bash window:
   ```bash
   source .venv/Scripts/activate
   uvicorn apps.api.main:app --reload
   ```
4. **Start frontend** in another window:
   ```bash
   cd apps/web
   npm run dev
   ```
5. Open http://localhost:3000 to use the UI (ensure `.env.local` contains `NEXT_PUBLIC_API_BASE_URL` and `NEXT_PUBLIC_API_KEY`).

## Session 2026-04 Kinoboxd Ops
### UX & Performance
- **Homepage:** Removed the “Top picks” SSR fetch (`apps/web/src/app/page.tsx`), so `/` no longer calls `/rankings` on first paint. Initial TTFB dropped from ~5s to ~1s.
- **Cohort detail:** Added `current_task_stage` column + Suspense fallback to show “Refreshing / Scraping / Computing” states. Enrichment now runs after sync finishes, keeping sync state “Idle” once rankings are ready.
- **Result limits & caching:** Default ranking fetch reduced to 50 rows; server-side caching now used outside demo mode to avoid redundant fetches.

### CI/CD & Deployments
- **Workflow:** `.github/workflows/ci.yml` now runs lint/build/test and, on pushes to `main`, deploys via SSH (appleboy action). Script steps: git fetch/reset, `npm ci` + `npm run build`, `pm2 reload`, `docker compose pull/up`, Alembic, restart API + Celery.
- **GitHub secrets:** Added repo-level `DO_SSH_HOST`, `DO_SSH_USER`, `DO_SSH_KEY` (deploy key with no passphrase). Any future secrets (PATs, etc.) go here.
- **Server SSH keys:**
  - `~/.ssh/kinoboxd-ci`: private key stored in GitHub secrets for the deploy job.
  - `~/.ssh/kinoboxd-github`: deploy key registered under Repo → Settings → Deploy keys. SSH config entry `github.com-kinoboxd` maps to this key; origin URL must be `git@github.com-kinoboxd:youngjaek/letterboxd-scraper.git`.
- **Troubleshooting lessons:** We hit “missing server host,” “private key is passphrase-protected,” and “repo not found” errors until we (a) created a passphrase-free key for CI, (b) trusted that key on the droplet (`authorized_keys`), and (c) added a GitHub Deploy key for the server so `git fetch` works.
- **Deploy time (~3 min):** Expected because we re-install node modules + rebuild Next.js + run Alembic per deploy. Future improvement: build artifacts/Docker images in CI, so the server only pulls prebuilt assets.

### Next steps / reminders
- Consider caching homepage featured data or removing any future heavy SSR calls.
- Automate artifact builds (Docker/Next export) to shorten deploys.
- Monitor CI runtimes; add alerts if deploy >5 min or fails due to SSH issues.
- When rotating keys: update `/root/.ssh/config`, `~/.ssh/authorized_keys`, GitHub Deploy keys, and repo secrets in tandem.

## Shutting everything down
- Press `Ctrl+C` in the frontend terminal to stop `npm run dev`.
- Press `Ctrl+C` in the API terminal to stop `uvicorn`.
- In the Docker Compose terminal, press `Ctrl+C` once to stop Redis + the worker gracefully; if they hang, press again.
- Docker Desktop can remain running, or quit it via its tray icon when you’re done.

## Notes
- The Celery worker relies on `.env.docker` for `DATABASE_URL`, so keep that file updated locally (it’s gitignored).
- If you change the Dockerfile or dependencies, rerun compose with `--build` to rebuild the worker image.
