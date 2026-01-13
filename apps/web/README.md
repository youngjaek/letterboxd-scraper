# Web Frontend Scaffold

Phase 3 ships a lightweight web client that talks to the FastAPI service under `apps/api`. This directory currently holds documentation while we decide whether to bootstrap the frontend with Next.js or Vite.

Planned steps (mirrors `docs/phase3_product_layer_plan.md`):

1. Initialize a TypeScript React app (Next.js preferred for SSR/ISR).
2. Configure `.env` consumption for the API base URL and feature flags.
3. Implement the initial views: cohort dashboard, ranking explorer + filters, saved lists grid, and run history timeline.
4. Wire up React Query/SWR to the API and add Storybook or unit tests for shared components.
5. Package the frontend as part of the Docker Compose stack for local and alpha deployments.

Until the tooling decision is finalized, this README marks the placeholder so the repo structure aligns with the development plan.
