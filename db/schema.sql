-- Normalized schema for Letterboxd cohort scraper

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    letterboxd_username TEXT UNIQUE NOT NULL,
    display_name TEXT,
    avatar_url TEXT,
    last_full_scrape_at TIMESTAMPTZ,
    last_incremental_scrape_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS films (
    id SERIAL PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    letterboxd_film_id INT UNIQUE,
    letterboxd_rating_count INT,
    letterboxd_fan_count INT,
    letterboxd_weighted_average NUMERIC(4, 2),
    release_year INT,
    release_date DATE,
    tmdb_id INT,
    tmdb_media_type TEXT,
    tmdb_show_id INT,
    tmdb_season_number INT,
    tmdb_episode_number INT,
    imdb_id TEXT,
    runtime_minutes INT,
    poster_url TEXT,
    overview TEXT,
    origin_countries JSONB,
    genres JSONB,
    tmdb_payload JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS films_tmdb_media_key ON films (tmdb_id, tmdb_media_type) WHERE tmdb_id IS NOT NULL AND tmdb_media_type IS NOT NULL;

CREATE TABLE IF NOT EXISTS ratings (
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    film_id INT REFERENCES films(id) ON DELETE CASCADE,
    rating NUMERIC(3, 1),
    rated_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    liked BOOLEAN DEFAULT FALSE,
    favorite BOOLEAN DEFAULT FALSE,
    diary_entry_url TEXT,
    PRIMARY KEY (user_id, film_id)
);

CREATE TABLE IF NOT EXISTS cohorts (
    id SERIAL PRIMARY KEY,
    label TEXT NOT NULL,
    seed_user_id INT REFERENCES users(id),
    definition JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cohort_members (
    cohort_id INT REFERENCES cohorts(id) ON DELETE CASCADE,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    depth INT NOT NULL,
    followed_at TIMESTAMPTZ,
    PRIMARY KEY (cohort_id, user_id)
);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id SERIAL PRIMARY KEY,
    cohort_id INT REFERENCES cohorts(id),
    run_type TEXT NOT NULL, -- full, incremental, follow_refresh
    started_at TIMESTAMPTZ DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS user_scrape_state (
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    last_page INT DEFAULT 1,
    last_cursor TEXT,
    last_status TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id)
);

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

CREATE TABLE IF NOT EXISTS film_rankings (
    cohort_id INT REFERENCES cohorts(id) ON DELETE CASCADE,
    strategy TEXT NOT NULL,
    film_id INT REFERENCES films(id) ON DELETE CASCADE,
    score NUMERIC NOT NULL,
    rank INT,
    params JSONB,
    computed_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (cohort_id, strategy, film_id)
);

CREATE TABLE IF NOT EXISTS ranking_insights (
    cohort_id INT REFERENCES cohorts(id) ON DELETE CASCADE,
    strategy TEXT NOT NULL,
    film_id INT REFERENCES films(id) ON DELETE CASCADE,
    timeframe_key TEXT NOT NULL,
    filters JSONB,
    watchers INT,
    avg_rating NUMERIC,
    watchers_percentile NUMERIC,
    rating_percentile NUMERIC,
    watchers_zscore NUMERIC,
    rating_zscore NUMERIC,
    cluster_label TEXT,
    bucket_label TEXT,
    computed_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (cohort_id, strategy, film_id, timeframe_key)
);

CREATE TABLE IF NOT EXISTS film_people (
    id SERIAL PRIMARY KEY,
    film_id INT REFERENCES films(id) ON DELETE CASCADE,
    person_id INT,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    credit_order INT,
    UNIQUE (film_id, role, person_id)
);

CREATE TABLE IF NOT EXISTS film_histograms (
    id SERIAL PRIMARY KEY,
    film_id INT REFERENCES films(id) ON DELETE CASCADE,
    cohort_id INT REFERENCES cohorts(id) ON DELETE CASCADE,
    bucket_label TEXT NOT NULL,
    count INT NOT NULL,
    computed_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (film_id, cohort_id, bucket_label)
);

-- Materialized view for cohort stats
CREATE MATERIALIZED VIEW IF NOT EXISTS cohort_film_stats AS
SELECT
    cm.cohort_id,
    r.film_id,
    COUNT(*) AS watchers,
    AVG(r.rating) AS avg_rating,
    SUM(r.rating) AS rating_sum,
    MIN(r.updated_at) AS first_rating_at,
    MAX(r.updated_at) AS last_rating_at
FROM ratings r
JOIN cohort_members cm ON cm.user_id = r.user_id
WHERE r.rating IS NOT NULL
GROUP BY cm.cohort_id, r.film_id;

CREATE INDEX IF NOT EXISTS idx_ratings_updated_at ON ratings(updated_at);
CREATE INDEX IF NOT EXISTS idx_cohort_members_cohort ON cohort_members(cohort_id);
CREATE INDEX IF NOT EXISTS idx_cohort_members_user ON cohort_members(user_id);
CREATE INDEX IF NOT EXISTS idx_cohort_film_stats_cohort ON cohort_film_stats(cohort_id);
