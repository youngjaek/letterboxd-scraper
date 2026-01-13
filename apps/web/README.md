# Letterboxd Cohort Web Client

This Next.js app consumes the FastAPI service under `apps/api` to provide dashboards, rankings, and saved filters outlined in `docs/phase3_product_layer_plan.md`.

## Getting Started

```bash
cd apps/web
npm install
npm run dev
```

Set `NEXT_PUBLIC_API_BASE_URL` in `.env.local` (defaults to `http://localhost:8000` so it works with `uvicorn apps.api.main:app --reload`).

## Structure

- `src/app/` — App Router entrypoints (`layout.tsx`, `page.tsx`).
- `src/app/(marketing)/page.tsx` — future marketing/landing routes.
- `src/components/` — shared UI primitives (to be added as features land).
- `tailwind.config.ts` — design tokens; update as we firm up the design system.

## Roadmap

- [ ] Cohort dashboard view with sync status + quick stats.
- [ ] Ranking explorer + filter drawer backed by `/cohorts/{id}/stats` API.
- [ ] Saved filter grid and export modal.
- [ ] Auth guard + session management (API tokens/passwordless login).
- [ ] Storybook or Chromatic visual regression coverage.
