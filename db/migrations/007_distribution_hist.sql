DROP INDEX IF EXISTS idx_cohort_film_stats_cohort;
DROP MATERIALIZED VIEW IF EXISTS cohort_film_stats;

CREATE MATERIALIZED VIEW cohort_film_stats AS
WITH aggregated AS (
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
        SUM(CASE WHEN r.rating = 0.5 THEN 1 ELSE 0 END) AS count_rating_0_5,
        SUM(CASE WHEN r.rating = 1.0 THEN 1 ELSE 0 END) AS count_rating_1_0,
        SUM(CASE WHEN r.rating = 1.5 THEN 1 ELSE 0 END) AS count_rating_1_5,
        SUM(CASE WHEN r.rating = 2.0 THEN 1 ELSE 0 END) AS count_rating_2_0,
        SUM(CASE WHEN r.rating = 2.5 THEN 1 ELSE 0 END) AS count_rating_2_5,
        SUM(CASE WHEN r.rating = 3.0 THEN 1 ELSE 0 END) AS count_rating_3_0,
        SUM(CASE WHEN r.rating = 3.5 THEN 1 ELSE 0 END) AS count_rating_3_5,
        SUM(CASE WHEN r.rating = 4.0 THEN 1 ELSE 0 END) AS count_rating_4_0,
        SUM(CASE WHEN r.rating = 4.5 THEN 1 ELSE 0 END) AS count_rating_4_5,
        SUM(CASE WHEN r.rating = 5.0 THEN 1 ELSE 0 END) AS count_rating_5_0,
        STDDEV_POP(r.rating) AS rating_stddev,
        VAR_POP(r.rating) AS rating_variance,
        MIN(r.updated_at) AS first_rating_at,
        MAX(r.updated_at) AS last_rating_at
    FROM ratings r
    JOIN cohort_members cm ON cm.user_id = r.user_id
    WHERE r.rating IS NOT NULL
    GROUP BY cm.cohort_id, r.film_id
)
SELECT
    aggregated.*,
    CASE
        WHEN aggregated.watchers <= 0 THEN 'unknown'
        WHEN aggregated.watchers > 0 AND (
            aggregated.count_rating_5_0::float / NULLIF(aggregated.watchers::float, 0)
        ) >= 0.40
        AND (
            GREATEST(
                aggregated.count_rating_4_5,
                aggregated.count_rating_4_0,
                aggregated.count_rating_3_5,
                aggregated.count_rating_3_0,
                aggregated.count_rating_2_5,
                aggregated.count_rating_2_0,
                aggregated.count_rating_1_5,
                aggregated.count_rating_1_0,
                aggregated.count_rating_0_5
            )::float / NULLIF(aggregated.watchers::float, 0)
        ) <= (
            aggregated.count_rating_5_0::float / NULLIF(aggregated.watchers::float, 0)
        ) / 2
        THEN 'masterpiece-consensus'
        WHEN aggregated.watchers > 0 AND (
            (aggregated.count_rating_5_0 + aggregated.count_rating_4_5 + aggregated.count_rating_4_0 + aggregated.count_rating_3_5 + aggregated.count_rating_3_0)::float
            / NULLIF(aggregated.watchers::float, 0)
        ) >= 0.70
        AND (
            aggregated.count_rating_5_0 + aggregated.count_rating_4_5
        )::float / NULLIF(aggregated.watchers::float, 0) BETWEEN 0.20 AND 0.40
        AND (
            aggregated.count_rating_1_5 + aggregated.count_rating_1_0 + aggregated.count_rating_0_5
        )::float / NULLIF(aggregated.watchers::float, 0) <= 0.15
        AND (
            aggregated.count_rating_3_5 + aggregated.count_rating_3_0
        ) >= (
            aggregated.count_rating_2_5 + aggregated.count_rating_2_0
        )
        THEN 'strong-favorite'
        WHEN aggregated.watchers > 0 AND (
            (aggregated.count_rating_5_0 + aggregated.count_rating_4_5 + aggregated.count_rating_4_0 + aggregated.count_rating_3_5 + aggregated.count_rating_3_0)::float
            / NULLIF(aggregated.watchers::float, 0)
        ) >= 0.60
        AND (
            aggregated.count_rating_1_5 + aggregated.count_rating_1_0 + aggregated.count_rating_0_5
        )::float / NULLIF(aggregated.watchers::float, 0) >= 0.10
        AND (
            aggregated.count_rating_5_0 + aggregated.count_rating_4_5
        )::float / NULLIF(aggregated.watchers::float, 0) < 0.35
        AND (
            aggregated.count_rating_1_5 + aggregated.count_rating_1_0 + aggregated.count_rating_0_5
        )::float / NULLIF(aggregated.watchers::float, 0) >= 0.4 * (
            aggregated.count_rating_5_0 + aggregated.count_rating_4_5
        )::float / NULLIF(aggregated.watchers::float, 0)
        THEN 'cult-darling'
        WHEN aggregated.watchers > 0 AND (
            (aggregated.count_rating_3_5 + aggregated.count_rating_3_0 + aggregated.count_rating_2_5 + aggregated.count_rating_2_0)::float
            / NULLIF(aggregated.watchers::float, 0)
        ) >= 0.75
        AND ABS(
            (aggregated.count_rating_3_5 + aggregated.count_rating_3_0)
            - (aggregated.count_rating_2_5 + aggregated.count_rating_2_0)
        )::float / NULLIF(aggregated.watchers::float, 0) <= 0.10
        AND (
            aggregated.count_rating_5_0 + aggregated.count_rating_4_5 + aggregated.count_rating_4_0
        )::float / NULLIF(aggregated.watchers::float, 0) <= 0.15
        AND (
            aggregated.count_rating_1_5 + aggregated.count_rating_1_0 + aggregated.count_rating_0_5
        )::float / NULLIF(aggregated.watchers::float, 0) <= 0.15
        THEN 'steady-crowdpleaser'
        WHEN aggregated.watchers > 0 AND (
            (aggregated.count_rating_3_5 + aggregated.count_rating_3_0 + aggregated.count_rating_2_5 + aggregated.count_rating_2_0)::float
            / NULLIF(aggregated.watchers::float, 0)
        ) >= 0.60
        AND (
            aggregated.count_rating_5_0 + aggregated.count_rating_4_5 + aggregated.count_rating_4_0
        )::float / NULLIF(aggregated.watchers::float, 0) BETWEEN 0.10 AND 0.20
        AND (
            aggregated.count_rating_1_5 + aggregated.count_rating_1_0 + aggregated.count_rating_0_5
        )::float / NULLIF(aggregated.watchers::float, 0) BETWEEN 0.10 AND 0.20
        AND ABS(
            (
                aggregated.count_rating_5_0 + aggregated.count_rating_4_5 + aggregated.count_rating_4_0
            ) - (
                aggregated.count_rating_1_5 + aggregated.count_rating_1_0 + aggregated.count_rating_0_5
            )
        )::float / NULLIF(aggregated.watchers::float, 0) <= 0.05
        THEN 'even-split'
        WHEN aggregated.watchers > 0 AND (
            aggregated.count_rating_5_0 + aggregated.count_rating_4_5 + aggregated.count_rating_4_0
        )::float / NULLIF(aggregated.watchers::float, 0) BETWEEN 0.20 AND 0.40
        AND (
            aggregated.count_rating_3_5 + aggregated.count_rating_3_0 + aggregated.count_rating_2_5 + aggregated.count_rating_2_0
        )::float / NULLIF(aggregated.watchers::float, 0) BETWEEN 0.20 AND 0.40
        AND (
            aggregated.count_rating_1_5 + aggregated.count_rating_1_0 + aggregated.count_rating_0_5
        )::float / NULLIF(aggregated.watchers::float, 0) BETWEEN 0.20 AND 0.40
        AND (
            GREATEST(
                aggregated.count_rating_5_0,
                aggregated.count_rating_4_5,
                aggregated.count_rating_4_0,
                aggregated.count_rating_3_5,
                aggregated.count_rating_3_0,
                aggregated.count_rating_2_5,
                aggregated.count_rating_2_0,
                aggregated.count_rating_1_5,
                aggregated.count_rating_1_0,
                aggregated.count_rating_0_5
            ) - LEAST(
                aggregated.count_rating_5_0,
                aggregated.count_rating_4_5,
                aggregated.count_rating_4_0,
                aggregated.count_rating_3_5,
                aggregated.count_rating_3_0,
                aggregated.count_rating_2_5,
                aggregated.count_rating_2_0,
                aggregated.count_rating_1_5,
                aggregated.count_rating_1_0,
                aggregated.count_rating_0_5
            )
        )::float / NULLIF(aggregated.watchers::float, 0) <= 0.15
        THEN 'wildcard'
        WHEN aggregated.watchers > 0 AND (
            aggregated.count_rating_1_5 + aggregated.count_rating_1_0 + aggregated.count_rating_0_5
        )::float / NULLIF(aggregated.watchers::float, 0) >= 0.40
        AND (
            aggregated.count_rating_5_0 + aggregated.count_rating_4_5 + aggregated.count_rating_4_0
        )::float / NULLIF(aggregated.watchers::float, 0) <= 0.10
        AND (
            aggregated.count_rating_1_5 + aggregated.count_rating_1_0 + aggregated.count_rating_0_5
        ) >= 1.6 * GREATEST(
            aggregated.count_rating_2_5 + aggregated.count_rating_2_0,
            aggregated.count_rating_3_5 + aggregated.count_rating_3_0,
            aggregated.count_rating_5_0 + aggregated.count_rating_4_5 + aggregated.count_rating_4_0
        )
        THEN 'consensus-bomb'
        WHEN aggregated.watchers > 0 AND (
            aggregated.count_rating_1_5 + aggregated.count_rating_1_0 + aggregated.count_rating_0_5 + aggregated.count_rating_2_5 + aggregated.count_rating_2_0
        )::float / NULLIF(aggregated.watchers::float, 0) >= 0.70
        AND (
            aggregated.count_rating_1_5 + aggregated.count_rating_1_0 + aggregated.count_rating_0_5
        )::float / NULLIF(aggregated.watchers::float, 0) BETWEEN 0.20 AND 0.40
        AND (
            aggregated.count_rating_5_0 + aggregated.count_rating_4_5 + aggregated.count_rating_4_0
        )::float / NULLIF(aggregated.watchers::float, 0) <= 0.20
        THEN 'general-dislike'
        WHEN aggregated.watchers > 0 AND (
            aggregated.count_rating_1_5 + aggregated.count_rating_1_0 + aggregated.count_rating_0_5
        )::float / NULLIF(aggregated.watchers::float, 0) >= 0.30
        AND (
            aggregated.count_rating_5_0 + aggregated.count_rating_4_5
        )::float / NULLIF(aggregated.watchers::float, 0) >= 0.10
        AND (
            aggregated.count_rating_3_5 + aggregated.count_rating_3_0 + aggregated.count_rating_2_5 + aggregated.count_rating_2_0
        )::float / NULLIF(aggregated.watchers::float, 0) <= 0.40
        AND LEAST(
            aggregated.count_rating_1_5 + aggregated.count_rating_1_0 + aggregated.count_rating_0_5,
            aggregated.count_rating_5_0 + aggregated.count_rating_4_5
        ) >= 0.25 * GREATEST(
            aggregated.count_rating_1_5 + aggregated.count_rating_1_0 + aggregated.count_rating_0_5,
            aggregated.count_rating_5_0 + aggregated.count_rating_4_5
        )
        THEN 'love-it-or-hate-it'
        ELSE 'unclassified'
    END AS distribution_label
FROM aggregated;

CREATE INDEX IF NOT EXISTS idx_cohort_film_stats_cohort ON cohort_film_stats(cohort_id);
