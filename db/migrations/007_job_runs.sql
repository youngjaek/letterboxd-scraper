-- Track Celery/automation runs for observability
CREATE TABLE IF NOT EXISTS job_runs (
    id SERIAL PRIMARY KEY,
    job_name TEXT NOT NULL,
    cohort_id INT REFERENCES cohorts(id),
    user_id INT REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'pending',
    payload JSONB,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    last_error TEXT
);
