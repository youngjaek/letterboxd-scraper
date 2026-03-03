# Kinoboxd Demo Launch Plan

This document captures the new direction for the project: shipping a polished, **read‑only demo** that showcases the product experience without relying on the legacy scraping pipeline. It exists so future Codex sessions (and collaborators) immediately know the context, even after the interactive history resets.

## Working Title & Domain

- **Product name:** Kinoboxd (winks at Letterboxd while emphasizing “kin,” i.e., trusted friends)
- **Public domain:** `kinoboxd.me` (register via the Namecheap `.me` promo, point DNS at DigitalOcean, and serve everything over HTTPS). If that exact domain is unavailable, fall back to a close variant (e.g., `kino-boxd.me` or `kinoboxdapp.me`) but keep “Kinoboxd” as the brand.
- **Hosting credits:** Use the $200 DigitalOcean credit for the demo droplet (and optionally Managed Postgres); apply the free Namecheap SSL as an alternative to Let’s Encrypt if desired.

## Demo Strategy

We are shifting from a scraper-driven private tool to a **static-data product demo** that proves the UX value to potential partners (especially Letterboxd). The goals:

1. Convince Letterboxd that Kinoboxd is a legitimate product worth granting API access to.
2. Let prospective users experience the interface (browse/search/filter friend-group rankings) without any scraping activity.
3. Collect a waitlist + testimonials showing real demand.

## Implementation Checklist

### 1. Lock Down Source & Secrets

- Move this repo to private (or re-clone into a private origin). Remove public forks/access.
- Rotate all API keys/secrets; eliminate `NEXT_PUBLIC_API_KEY` usage in the web app.
- Create a long-lived `demo-release` branch inside the private repo for the deployment artifact. Day-to-day work can continue on `main`, but only cherry-pick read-only features into `demo-release`.

### 2. Add Demo Mode

- Introduce a `DEMO_MODE` flag shared by FastAPI + Next.js.
- Environment variables:
  - `DEMO_MODE=1` → backend/API enforces read-only behavior.
  - `NEXT_PUBLIC_DEMO_MODE=1` (or `DEMO_MODE=1` at build time) → frontend hides management controls + shows demo banners.
- When enabled:
  - Disable or hide any endpoint that kicks off scrapes, enrichment, or destructive actions (`/cohorts/{id}/sync`, `/sync/stop`, DELETEs, etc.). Either remove the routes entirely or guard them behind an internal admin token that never reaches the public build.
  - Strip “Sync now,” “Stop,” and “Delete” actions from the UI (replace with explanatory copy).
  - Display a banner noting that the data comes from Alexy’s cohort and that live syncs will require official Letterboxd API access.

### 3. Seed Demo Data

- Use our existing scrapers locally to populate Postgres with Alexy’s cohort (only for internal use), then snapshot that DB.
- Curate compelling saved filters: “Top 2020s Gems,” “Consensus Breakers,” “Cult Favourites,” etc. Store them so the homepage always has interesting slices without further computation.
- Write a lightweight job/script to import refreshed CSVs when we need to update the demo (no public scrape controls).

### 4. Deploy the Read-Only Stack

- Provision a DigitalOcean droplet (2 vCPU / 4 GB RAM is plenty) via the $200 credit.
- Deploy the repo using `docker compose -f docker-compose.dev.yml up -d` (Redis + API + worker + web). In demo mode the worker/stats containers mainly serve as API dependencies; long-running scrapes stay disabled.
- Configure the `.me` domain to point at the droplet (A/AAAA records) and obtain TLS certificates (either the free Namecheap cert or DO’s Let’s Encrypt integration). Force HTTPS.
- Lock down CORS and firewall rules so only the web front-end hits the API; no open Celery ports.
- Add TMDB/Letterboxd attribution footer + a privacy notice explaining that the demo uses preloaded data.

### 5. Marketing & Advocacy Assets

- Build a simple landing section on the homepage (or separate `/about` page) that explains:
  - What Kinoboxd does.
  - Screenshots/video of key flows.
  - A waitlist/signup form (Netlify Forms, ConvertKit, or a DIY FastAPI endpoint).
  - Quotes from Letterboxd users who want this functionality.
- Capture site analytics + waitlist metrics. These numbers, plus testimonials, will power the outreach email/petition to `api@letterboxd.com`.
- Draft an outreach packet (one-pager PDF or Notion doc) summarizing the product, demo URL, compliance posture, and user demand.

### 6. Ongoing Ops

- Keep `demo-release` updated with any UI polish or storytelling improvements (no scraping code needed).
- Periodically refresh the demo dataset manually to show recent activity.
- Monitor uptime/logs; ensure no sensitive data is logged or exposed.
- Track interest (waitlist size, unique visitors) and update the outreach pitch as numbers grow.

## Outreach Plan

1. Quiet launch to trusted friends for feedback; fix visual/content issues.
2. Publicly share the demo + waitlist to gather testimonials.
3. Once momentum builds, email Letterboxd with:
   - Demo link + video.
   - Waitlist stats/user quotes.
   - Assurance that the current demo is read-only and we seek API access to scale responsibly.
4. Optionally circulate a petition/support letter among well-known Letterboxd users to bolster the request.

## What Not To Do

- Do **not** expose scraping endpoints or admin controls in the public UI.
- Do **not** ship secrets to the browser (no `NEXT_PUBLIC_*` credentials).
- Do **not** resume automated scrapes against Letterboxd without their consent; all updates should be manual imports until API access is granted.

With this plan captured in the repo, future Codex sessions can immediately pick up the demo workstream without recreating the roadmap from memory. Ensure this file stays up to date as decisions evolve.
