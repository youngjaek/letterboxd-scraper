CREATE TABLE IF NOT EXISTS scrape_run_members (
    run_id INT REFERENCES scrape_runs(id) ON DELETE CASCADE,
    username TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    mode TEXT NOT NULL DEFAULT 'incremental',
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    error TEXT,
    PRIMARY KEY (run_id, username)
);
