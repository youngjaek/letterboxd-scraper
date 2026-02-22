# Database Migrations

We now manage schema changes with [Alembic](https://alembic.sqlalchemy.org/).

## Setup

1. Install the new dependency (`pip install -e .` or `poetry install`).
2. Ensure your shell can import the project (`PYTHONPATH=src` or activate the venv).
3. Provide a database URL via either:
   - `DATABASE_URL`/entries in `config/default.toml` (picked up by `letterboxd_scraper.config`), or
   - `ALEMBIC_DATABASE_URL` (highest priority).

## Create a Revision

```bash
alembic revision --autogenerate -m "describe change"
```

## Apply Migrations

```bash
alembic upgrade head
```

Use `alembic downgrade -1` to step back.

## Notes

- The existing SQL files in `db/migrations/` remain for reference, but new work should go through Alembic revisions under `alembic/versions/`.
- The Alembic env loads the same settings as the CLI (respecting `.env`/TOML), so you don’t need to duplicate connection info.
