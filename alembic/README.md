# Alembic Migrations

This directory was initialized to manage schema changes via Alembic. Run commands from the project root with `PYTHONPATH=src` (or an active venv) so the env script can import `letterboxd_scraper`.

Common commands:

```bash
# autogenerate a new revision
alembic revision --autogenerate -m "describe change"

# apply migrations
alembic upgrade head

# rollback
alembic downgrade -1
```

The env script loads database settings from `config/default.toml` plus environment variables, the same way the CLI does. You can also override using `ALEMBIC_DATABASE_URL`.
