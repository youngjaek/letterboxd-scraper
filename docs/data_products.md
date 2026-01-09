# Cohort Data Products & Insights

With the scrape/enrichment pipeline in place we now have normalized tables that track cohort membership, ratings (with likes/favorites), per-film aggregates, TMDB metadata, and histograms. This doc lays out how to turn that data into meaningful products, how to score films beyond simple averages, and what engineering patterns (caching, precomputation) keep the experience fast.

---

## 1. Core Ranking Surfaces

| Surface | Description | Inputs |
| --- | --- | --- |
| Cohort Top N (50/100/250) | Baseline Bayesian/Wilson rankings for the entire cohort. | `cohort_film_stats`, `film_rankings`, likes/favorites |
| Member-centric views | Re-scope rankings to “me + people I follow,” or any saved mini-cohort. | same + `cohort_members` filters |
| Temporal slices | Top films by release year (e.g., 2020s) or watched date (using `ratings.updated_at` / `rated_at`). | `cohort_film_stats`, `films.release_year`, `ratings.updated_at` |
| List intersections | Filter rankings against Letterboxd lists, filmographies, festival slates. | `film_rankings` + subset tables |

### Scoring beyond averages

To make rankings predictive (e.g., “what will I likely rate?”), incorporate:

1. **Bayesian mean** (already implemented):
   ```
   R = cohort_avg_rating
   v = cohort_watchers
   m = configurable vote floor (e.g., 50)
   C = overall cohort mean
   score = (v/(v+m)) * R + (m/(v+m)) * C
   ```
2. **Engagement factors** (likes/favorite ratios):
   - `like_rate = likes / watchers`
   - `favorite_rate = favorites / watchers`
3. **Distribution shape** (histogram-derived features):
   - `variance` / `std_dev` from per-bucket counts.
   - `skewness` to distinguish “polarizing” vs “consensus” titles.

An extended score might look like:
```
score = w_bayes * bayesian_mean
      + w_like  * z(like_rate)
      + w_fav   * z(favorite_rate)
      + w_consensus * consensus_bonus
      - w_volatility * z(std_dev)
```

Where:
- `consensus_bonus = 1` when ≥X% of watchers rated ≥4; 0 otherwise.
- `z()` is a z-score within the cohort to normalize features.

This captures the John Wick vs Lady Bird nuance: even if averages match, John Wick’s histogram shows a massive mode at 3–4 stars with few high ratings, so its `consensus_bonus` is low and `std_dev` moderate; Lady Bird’s distribution leans more toward higher ratings, increasing the consensus bonus and lowering volatility. The ranking would therefore put Lady Bird above John Wick for cohorts that value high-end enthusiasm, while a “crowd pleaser” strategy might do the opposite (reward dense middle ratings).

### Distribution-aware predictions

For personalized recommendations, compute the probability you’ll rate a film at each star level based on collaborative filtering heuristics:

1. **Histogram similarity**: compare your historical rating distribution to each film’s cohort histogram (e.g., if you rarely give 5s, downplay films with many 5s).
2. **Conditional expectation**:
   ```
   expected_rating_user = Σ (bucket_midpoint * P_user(bucket) * P_film(bucket))
   ```
   Where `P_user` is the probability you rate something in that bucket (from your history) and `P_film` is the cohort distribution for the film.

This yields “you’ll probably rate John Wick 3.5” vs “Lady Bird 4.0” even if their averages match.

---

## 2. Divergence & Consensus

- **Cohort vs Letterboxd delta:** use `films.letterboxd_weighted_average` and global histograms to surface films where cohort sentiment differs.
- **Consensus meter:** categorize films:
  - `Unanimous Praise`: ≥80% rated ≥4.
  - `Crowd Pleaser`: majority between 3–4, low variance.
  - `Divisive`: high variance, multi-modal histogram.
  - `Marmite`: bimodal distribution.
- **Sentiment shifts over time:** track `cohort_film_stats.last_rating_at` to see if opinions change (requires storing historical snapshots or time-series).

Implementation tip: store consensus labels in `ranking_insights` to avoid recomputing.

---

## 3. Likes & Engagement

- **Likes-only discoveries:** highlight titles with many likes/favorites but few ratings (often unrated rewatches or festival diary entries).
- **Engagement-weighted rankings:** treat `like_rate` and `favorite_rate` as boosting factors in the score.
- **Activity digests:** “Films most liked this week” using `ratings.updated_at`.

Engineering: maintain materialized views that aggregate likes/favorites per film per week; use incremental-refresh strategy similar to `cohort_film_stats`.

---

## 4. People Insights

- **Top directors/actors**: join `film_people` (populated via enrichment) with `film_rankings`. Compute:
  - Weighted average of their films’ cohort scores.
  - Count of films in top percentile per person.
- **Collaboration score:** using bipartite graphs, find director-actor pairs with multiple high-ranked films.
- **Emerging voices:** filter for release year ≥ 2020 and directors with ≥2 films to surface new favorites.

Engineering: add indexes on `film_people(person_id, film_id)` and precompute aggregates into `person_stats` tables for fast queries.

---

## 5. Temporal Analytics

- **Recent activity feed:** sort `ratings.updated_at` descending, join with film metadata, and show what the cohort rated today/yesterday/this week.
- **Watch streaks / bursts:** compute per-user rolling counts; surface “Top binge-watchers” or “Users on a streak.”
- **Rewatch detection:** if future diary ingestion revives `rated_at`, track multiple entries per user-film combo with later timestamps.

Engineering: store `user_activity` table (user_id, film_id, action, timestamp) derived from `ratings` to drive feeds; index on timestamp.

---

## 6. Smart Buckets & Segmentation

- **Percentile buckets** (already in `rank buckets`): maintain dynamic cuts (90th percentile, etc.).
- **Engagement clusters:** define clusters by `(watchers, avg_rating)` pairs; store label per film.
- **Taste clusters:** represent each user as a vector of z-scored ratings on popular films, run clustering (k-means or spectral) offline, and tag users. Use this for “Critic pods” or personalized recommendations.

Engineering: run clustering offline (e.g., nightly job), store assignments in `user_clusters`, expose via API/CLI.

---

## 7. Cross-Cohort Comparisons

- **Overlap heatmaps:** compute Jaccard similarity of top N lists across cohorts.
- **Consensus vs dissent lists:** e.g., “Films Cohort A loves that Cohort B hates.”
- **Regional breakdowns:** if cohorts map to geographies, show regional taste differences.

Engineering: precompute cross-cohort comparisons if cohorts are few; for many combinations, cache results lazily with TTL (see caching section).

---

## 8. Engineering & Performance Strategy

### Schema highlights
- `ratings`: `(user_id, film_id, rating, liked, favorite, updated_at, rated_at)` — base events.
- `cohort_film_stats`: per cohort aggregates (watchers, avg rating, first/last rating timestamps).
- `film_rankings`: cached scores per strategy.
- `film_histograms`: per-bucket counts (Letterboxd).
- `film_people`: mapping for director/actor insights.
- `ranking_insights`: derived labels (smart buckets, divergence flags).

### Caching & Precomputation
1. **Materialized views**: `cohort_film_stats`, `film_rankings`, `ranking_insights` should be refreshed after scrapes. Use PostgreSQL materialized views or tables maintained by the CLI.
2. **Redis/memcached**: cache expensive query results (e.g., divergence lists, cross-cohort comparisons) with TTL. Key design: `cohort:{id}:strategy:{name}:slice:{params_hash}`.
3. **Incremental refresh**: after `scrape`, enqueue jobs to recompute only affected cohorts. Track touched film IDs to limit recomputation scope.

### Handling heavy SQL
- **Partitioning**: If cohorts get large, partition `ratings` by `cohort_id` or `user_id` to speed scans.
- **Indices**: ensure composite indexes on `(cohort_id, film_id)`, `(user_id, film_id)`, `(ratings.updated_at)`, `(films.release_year)`.
- **Async workers**: offload long-running analyses (e.g., clustering) to background jobs with progress tracking.
- **Explain/Benchmark**: regularly run `EXPLAIN ANALYZE` on key queries; keep a “slow query” dashboard.

### API/CLI usage patterns
- **CLI bundling**: keep `scrape → enrich → stats refresh → rank compute` as a chain; each writes to tables consumed by the insights features.
- **SaaS/API**: expose endpoints like `/cohorts/{id}/rankings?strategy=engagement&release_year>=2020` or `/cohorts/{id}/divergences`.
- **Telemetry**: keep recording `scrape_runs` and extend to `insight_runs` so you can monitor refresh health.

---

## 9. Roadmap Suggestions

1. **Phase 1 (“Insight Pack”)**
   - Implement engagement-enhanced ranking score.
   - Add divergence lists and consensus labels.
   - Build “recent activity” digest.

2. **Phase 2 (“People & clusters”)**
   - Populate `film_people` coverage via enrichment audits.
   - Add director/actor rankings.
   - Run user clustering + tag users.

3. **Phase 3 (“Cross-cohort & productization”)**
   - Multi-cohort comparisons, shareable embeds.
   - Caching layer + basic API to power dashboards.
   - Notification/digest service for new films.

4. **Phase 4 (“ML & personalization”)**
   - Implement histogram-based rating predictions.
   - Use collaborative filtering or matrix factorization to recommend unseen films within cohorts.
   - Tie recommendations to dynamic cohorts (“Critics like you”).

---

## Appendix: Example SQL Snippets

### Cohort vs Letterboxd delta
```sql
SELECT
  f.slug,
  cfs.avg_rating AS cohort_rating,
  f.letterboxd_weighted_average AS lb_rating,
  (cfs.avg_rating - f.letterboxd_weighted_average) AS delta,
  cfs.watchers
FROM cohort_film_stats cfs
JOIN films f ON f.id = cfs.film_id
WHERE cfs.cohort_id = :cohort
ORDER BY delta DESC
LIMIT 50;
```

### Consensus classification (pseudo)
```sql
WITH buckets AS (
  SELECT
    film_id,
    SUM(CASE WHEN rating >= 4 THEN 1 ELSE 0 END) AS high_votes,
    COUNT(*) AS total_votes,
    stddev_pop(rating) AS std_dev
  FROM ratings
  WHERE cohort_id = :cohort
  GROUP BY film_id
)
SELECT
  film_id,
  CASE
    WHEN high_votes::float / total_votes >= 0.8 THEN 'Unanimous Praise'
    WHEN std_dev <= 0.4 THEN 'Crowd Pleaser'
    WHEN std_dev >= 1.0 THEN 'Divisive'
    ELSE 'Mixed'
  END AS label
FROM buckets;
```

---

By layering these insights and engineering practices on top of the data pipeline, we can deliver a rich set of cohort-aware experiences: from “Top 2024 releases our friends love” to “Directors we adore” to divergence dashboards—all while keeping runtimes manageable via caching and focused recomputation. This document should serve as the north-star backlog for turning raw scrape data into a compelling product. 
