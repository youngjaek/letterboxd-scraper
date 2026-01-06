-- Add TMDB metadata columns and supporting tables
ALTER TABLE films
    ADD COLUMN release_date DATE,
    ADD COLUMN tmdb_id INT UNIQUE,
    ADD COLUMN imdb_id TEXT,
    ADD COLUMN runtime_minutes INT,
    ADD COLUMN overview TEXT,
    ADD COLUMN origin_countries JSONB,
    ADD COLUMN genres JSONB,
    ADD COLUMN tmdb_payload JSONB;

ALTER TABLE ratings
    ADD COLUMN liked BOOLEAN DEFAULT FALSE,
    ADD COLUMN favorite BOOLEAN DEFAULT FALSE;

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
