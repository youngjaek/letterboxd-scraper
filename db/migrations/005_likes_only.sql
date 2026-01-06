-- Allow unrated likes to be stored in ratings table.
ALTER TABLE ratings ALTER COLUMN rating DROP NOT NULL;

-- Recreate cohort_film_stats to ignore unrated entries.
DROP INDEX IF EXISTS idx_cohort_film_stats_cohort;
DROP MATERIALIZED VIEW IF EXISTS cohort_film_stats;

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

CREATE INDEX IF NOT EXISTS idx_cohort_film_stats_cohort ON cohort_film_stats(cohort_id);
