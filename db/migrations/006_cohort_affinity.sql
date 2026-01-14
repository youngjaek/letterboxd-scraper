-- Refresh cohort_film_stats to include enthusiasm + histogram aggregates.
DROP INDEX IF EXISTS idx_cohort_film_stats_cohort;
DROP MATERIALIZED VIEW IF EXISTS cohort_film_stats;

CREATE MATERIALIZED VIEW cohort_film_stats AS
SELECT
    cm.cohort_id,
    r.film_id,
    COUNT(*) AS watchers,
    AVG(r.rating) AS avg_rating,
    SUM(r.rating) AS rating_sum,
    SUM(CASE WHEN r.liked THEN 1 ELSE 0 END) AS likes_count,
    SUM(CASE WHEN r.favorite THEN 1 ELSE 0 END) AS favorites_count,
    SUM(CASE WHEN r.rating >= 4.0 THEN 1 ELSE 0 END)::float / NULLIF(COUNT(*), 0) AS high_rating_pct,
    SUM(CASE WHEN r.rating <= 2.0 THEN 1 ELSE 0 END)::float / NULLIF(COUNT(*), 0) AS low_rating_pct,
    SUM(CASE WHEN r.rating >= 4.5 THEN 1 ELSE 0 END) AS count_rating_gte_4_5,
    SUM(CASE WHEN r.rating >= 4.0 AND r.rating < 4.5 THEN 1 ELSE 0 END) AS count_rating_4_0_4_5,
    SUM(CASE WHEN r.rating >= 3.5 AND r.rating < 4.0 THEN 1 ELSE 0 END) AS count_rating_3_5_4_0,
    SUM(CASE WHEN r.rating >= 3.0 AND r.rating < 3.5 THEN 1 ELSE 0 END) AS count_rating_3_0_3_5,
    SUM(CASE WHEN r.rating >= 2.5 AND r.rating < 3.0 THEN 1 ELSE 0 END) AS count_rating_2_5_3_0,
    SUM(CASE WHEN r.rating < 2.5 THEN 1 ELSE 0 END) AS count_rating_lt_2_5,
    STDDEV_POP(r.rating) AS rating_stddev,
    VAR_POP(r.rating) AS rating_variance,
    MIN(r.updated_at) AS first_rating_at,
    MAX(r.updated_at) AS last_rating_at
FROM ratings r
JOIN cohort_members cm ON cm.user_id = r.user_id
WHERE r.rating IS NOT NULL
GROUP BY cm.cohort_id, r.film_id;

CREATE INDEX IF NOT EXISTS idx_cohort_film_stats_cohort ON cohort_film_stats(cohort_id);
