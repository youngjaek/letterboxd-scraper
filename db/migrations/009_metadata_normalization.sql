-- Normalize TMDB metadata: extract genres/countries, build people directory, and drop raw payload blobs.

BEGIN;

ALTER TABLE films
    ADD COLUMN IF NOT EXISTS tmdb_synced_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS tmdb_not_found BOOLEAN DEFAULT FALSE;


CREATE TABLE IF NOT EXISTS people (
    id SERIAL PRIMARY KEY,
    tmdb_id INT UNIQUE,
    name TEXT NOT NULL,
    profile_url TEXT,
    known_for_department TEXT,
    tmdb_synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS genres (
    id SERIAL PRIMARY KEY,
    tmdb_id INT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS film_genres (
    film_id INT REFERENCES films(id) ON DELETE CASCADE,
    genre_id INT REFERENCES genres(id) ON DELETE CASCADE,
    PRIMARY KEY (film_id, genre_id)
);

CREATE INDEX IF NOT EXISTS idx_film_genres_genre ON film_genres(genre_id);

CREATE TABLE IF NOT EXISTS countries (
    code TEXT PRIMARY KEY,
    name TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS film_countries (
    film_id INT REFERENCES films(id) ON DELETE CASCADE,
    country_code TEXT REFERENCES countries(code) ON DELETE CASCADE,
    PRIMARY KEY (film_id, country_code)
);

CREATE INDEX IF NOT EXISTS idx_film_countries_country ON film_countries(country_code);

ALTER TABLE film_people
    RENAME COLUMN person_id TO tmdb_person_id;

ALTER TABLE film_people
    DROP CONSTRAINT IF EXISTS film_people_film_id_role_person_id_key;

ALTER TABLE film_people
    ADD COLUMN person_id INT;

ALTER TABLE film_people
    ADD CONSTRAINT film_people_person_fk
        FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE CASCADE;

-- Seed the people table from existing film_people rows.
INSERT INTO people (tmdb_id, name)
SELECT DISTINCT fp.tmdb_person_id, fp.name
FROM film_people fp
WHERE fp.tmdb_person_id IS NOT NULL
ON CONFLICT (tmdb_id) DO UPDATE SET
    name = EXCLUDED.name,
    updated_at = NOW();

INSERT INTO people (tmdb_id, name)
SELECT DISTINCT fp.tmdb_person_id, fp.name
FROM film_people fp
WHERE fp.tmdb_person_id IS NULL;

UPDATE film_people fp
SET person_id = p.id
FROM people p
WHERE (fp.tmdb_person_id IS NOT NULL AND p.tmdb_id = fp.tmdb_person_id)
   OR (fp.tmdb_person_id IS NULL AND p.tmdb_id IS NULL AND p.name = fp.name);

ALTER TABLE film_people
    ALTER COLUMN person_id SET NOT NULL;

ALTER TABLE film_people
    ADD CONSTRAINT film_people_unique_role UNIQUE (film_id, role, person_id);

ALTER TABLE film_people
    DROP COLUMN name,
    DROP COLUMN tmdb_person_id;

WITH genre_entries AS (
    SELECT
        f.id AS film_id,
        (genre ->> 'id')::INT AS genre_tmdb_id,
        genre ->> 'name' AS genre_name
    FROM films f
    CROSS JOIN LATERAL jsonb_array_elements(COALESCE(f.genres, '[]'::jsonb)) AS genre
    WHERE (genre ->> 'id') IS NOT NULL
)
INSERT INTO genres (tmdb_id, name)
SELECT DISTINCT genre_tmdb_id, genre_name
FROM genre_entries
WHERE genre_tmdb_id IS NOT NULL
ON CONFLICT (tmdb_id) DO UPDATE SET
    name = EXCLUDED.name,
    updated_at = NOW();

WITH genre_entries AS (
    SELECT
        f.id AS film_id,
        (genre ->> 'id')::INT AS genre_tmdb_id
    FROM films f
    CROSS JOIN LATERAL jsonb_array_elements(COALESCE(f.genres, '[]'::jsonb)) AS genre
    WHERE (genre ->> 'id') IS NOT NULL
)
INSERT INTO film_genres (film_id, genre_id)
SELECT DISTINCT ge.film_id, g.id
FROM genre_entries ge
JOIN genres g ON g.tmdb_id = ge.genre_tmdb_id
ON CONFLICT DO NOTHING;

WITH country_entries AS (
    SELECT
        f.id AS film_id,
        UPPER(country ->> 'iso_3166_1') AS country_code,
        country ->> 'name' AS country_name
    FROM films f
    CROSS JOIN LATERAL jsonb_array_elements(COALESCE(f.origin_countries, '[]'::jsonb)) AS country
    WHERE (country ->> 'iso_3166_1') IS NOT NULL
),
country_dedup AS (
    SELECT
        country_code,
        MAX(country_name) FILTER (WHERE country_name IS NOT NULL) AS country_name
    FROM country_entries
    WHERE country_code IS NOT NULL
    GROUP BY country_code
)
INSERT INTO countries (code, name)
SELECT country_code, country_name
FROM country_dedup
ON CONFLICT (code) DO UPDATE SET
    name = COALESCE(EXCLUDED.name, countries.name),
    updated_at = NOW();

WITH country_entries AS (
    SELECT
        f.id AS film_id,
        UPPER(country ->> 'iso_3166_1') AS country_code
    FROM films f
    CROSS JOIN LATERAL jsonb_array_elements(COALESCE(f.origin_countries, '[]'::jsonb)) AS country
    WHERE (country ->> 'iso_3166_1') IS NOT NULL
)
INSERT INTO film_countries (film_id, country_code)
SELECT DISTINCT ce.film_id, ce.country_code
FROM country_entries ce
WHERE ce.country_code IS NOT NULL
ON CONFLICT DO NOTHING;

-- Preserve tmdb_not_found information before dropping payload blob.
UPDATE films
SET tmdb_not_found = TRUE
WHERE (tmdb_payload ->> 'tmdb_not_found')::BOOLEAN IS TRUE;

ALTER TABLE film_people
    VALIDATE CONSTRAINT film_people_person_fk;

ALTER TABLE films
    DROP COLUMN IF EXISTS origin_countries,
    DROP COLUMN IF EXISTS genres,
    DROP COLUMN IF EXISTS tmdb_payload;

COMMIT;
