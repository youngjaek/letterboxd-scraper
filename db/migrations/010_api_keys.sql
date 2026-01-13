-- Add API key storage for authenticated API usage.

BEGIN;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS api_key TEXT,
    ADD COLUMN IF NOT EXISTS api_key_hash TEXT;

COMMIT;
