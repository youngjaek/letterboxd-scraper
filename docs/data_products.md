# Cohort Data Products & Insights

With the scrape/enrichment pipeline in place we now have normalized tables that track cohort membership, ratings (with likes/favorites), per-film aggregates, TMDB metadata, and histograms. This doc lays out how to turn that data into meaningful products, how to score films beyond simple averages, and what engineering patterns (caching, precomputation) keep the experience fast.

---

## 1. Core Ranking Surfaces

| Surface | Description | Inputs |
| --- | --- | --- |
| Cohort Top N (50/100/250) | Baseline Bayesian/Wilson rankings for the entire cohort. | `cohort_film_stats`, `film_rankings`, likes/favorites |
| Member-centric views | Re-scope rankings to “me + people I follow,” or any saved mini-cohort. | same + `cohort_members` filters |
| Temporal slices | Top films by release year (e.g., 2020s) or watched date (once diary/RSS data is available). | `cohort_film_stats`, `films.release_year`, `ratings.rated_at` |
| List intersections | Filter rankings against Letterboxd lists, filmographies, festival slates. | `film_rankings` + subset tables |
| **Advanced search** | UI/API that exposes filters across every metric: average rating range, Bayesian score range, watchers thresholds, histogram-derived consensus, release dates, runtime, likes/favorites, directors, etc. Each filter combo returns paginated rankings and supports CSV export for Letterboxd import. | All tables above + search index / cache |

### Ranking thresholds & pagination

- **Watchers floor**: default to `watchers >= 5` (configurable). Provide toggles like “include deep cuts” to lower the floor.
- **Pagination**: serve rankings via cursor-based pagination, e.g., `/rankings?offset=0&limit=50`. Under the hood, either:
  - Materialize scores into `film_rankings` and page over them with indexes (`cohort_id, strategy, score DESC, film_id`).
  - Use keyset pagination (e.g., `WHERE (score, film_id) < (:last_score, :last_id)`).
- **Advanced filters**: apply WHERE clauses on the materialized table (e.g., `score BETWEEN X AND Y`, `watchers BETWEEN A AND B`, `std_dev <= Z`). Precompute histogram stats (std_dev, skewness, high_rating_pct) into `ranking_insights` to avoid recomputing per request.
- **Export**: once a filter is applied, offer `export csv` that streams the filtered rows; reuse the existing export service but allow dynamic filters rather than precomputed top N.

### Scoring beyond averages

The Phase 3 UI ships with a concrete “cohort affinity” score that bakes in popularity, like/favourite enthusiasm, and histogram shape instead of relying on a single Bayesian mean. For each `(cohort_id, film_id)` we compute:

- `avg_rating_z`: average rating normalized per cohort.
- `log_watchers_z`: log₁₀ of watcher counts (capped at `<=1.0`) so runaway popularity helps but cannot swamp small-yet-beloved films.
- `favorite_rate_z` and `like_rate_z`: per-watcher enthusiasm signals with favourites weighted more heavily.
- `consensus_strength = high_rating_pct - low_rating_pct`: keeps steady excellence ahead of mixed reactions.
- `distribution_bonus`: derived from histogram labels (strong-left, left, balanced, right, bimodal, multimodal). Strong-left = +0.30, left = +0.15, balanced = 0, bimodal = context-dependent bonus/penalty, right-skewed = negative.

Score formula:
```
score =
    0.35 * avg_rating_z
  + 0.20 * log_watchers_z
  + 0.25 * favorite_rate_z
  + 0.10 * like_rate_z
  + 0.10 * distribution_bonus
  + 0.10 * consensus_strength
```

Because every component is normalized within the cohort, a film with 200 ratings at 4.3 and a huge 5★ share can outrank a 20-rating 4.7 title: the watchers term plus consensus signals outweigh a narrow average lead. Conversely, filters (“obscure gems,” “polarizing,” etc.) can zero in on low-watchers/high-favourite slices without redefining the canonical score.

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

- **Recent activity feed:** sort `ratings.updated_at` descending to show what was scraped recently (note: this is scrape timestamp, not watch date; explicitly label it as “last logged by the cohort”). When diary/RSS data is available, prefer `ratings.rated_at` for “watched on” slices.
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
- `ratings`: `(user_id, film_id, rating, liked, favorite, updated_at, rated_at)` — base events (`updated_at` = scrape timestamp; `rated_at` only populated when diary/RSS supplies watch date).
- `cohort_film_stats`: per cohort aggregates (watchers, avg rating, first/last rating timestamps).
- `film_rankings`: cached scores per strategy.
- `film_histograms`: per-bucket counts (Letterboxd).
- `film_people`: mapping for director/actor insights.
- `ranking_insights`: derived labels (smart buckets, divergence flags).

### Caching & Precomputation
1. **Materialized views**: `cohort_film_stats`, `film_rankings`, `ranking_insights`, and `search_rankings` (optional) should be refreshed after scrapes. Keep them denormalized so the advanced search is a single indexed SELECT.
2. **Redis/memcached**: cache expensive query results (e.g., divergence lists, cross-cohort comparisons, advanced search filter combos) with TTL. Key design: `cohort:{id}:strategy:{name}:slice:{params_hash}`.
3. **Incremental refresh**: after `scrape`, enqueue jobs to recompute only affected cohorts. Track touched film IDs to limit recomputation scope and warm caches.
4. **Pre-aggregated search docs**: consider storing a JSONB column per film in `film_rankings` with frequently-used metrics (like high_rating_pct, std_dev). This speeds up advanced filtering without rejoining histograms.
5. **Background warmers**: for popular filter combos (“Top 2024 with watchers≥25”), precompute and cache so the UI is instant.

### Handling heavy SQL
- **Partitioning**: If cohorts get large, partition `ratings` by `cohort_id` or `user_id` to speed scans.
- **Indices**: ensure composite indexes on `(cohort_id, film_id)`, `(user_id, film_id)`, `(ratings.updated_at)`, `(films.release_year)`, `(film_rankings.cohort_id, strategy, score DESC, film_id)`.
- **Search indexes**: for advanced filters, consider a specialized search table (or use PG `BRIN`/`GIN` indexes) covering numeric ranges (watchers, score, release_year) and JSONB attributes (genres, directors).
- **Async workers**: offload long-running analyses (e.g., clustering, cross-cohort comparisons) to background jobs with progress tracking.
- **Explain/Benchmark**: regularly run `EXPLAIN ANALYZE` on key queries; keep a “slow query” dashboard.

---

## 10. Similarity & Probabilistic Features

### User similarity

1. **Vector representation**: create user vectors using either:
   - Raw ratings on popular films (centered and normalized).
   - Embeddings from matrix factorization (ALS) or neural collaborative filtering.
2. **Similarity metrics**:
   - **Cosine similarity** for continuous ratings.
   - **Pearson correlation** to discount global mean.
   - **Jaccard** on like/favorite sets.
3. **Use cases**:
   - “Critics most aligned with you” panel.
   - Weighted recommendations (mix top similar users’ favorite films).
   - Cohort subgroups (“cluster of horror lovers”).

Engineering: compute similarity offline (nightly) and store top-K neighbors per user. Use `ratings.updated_at` to invalidate neighbors when enough new data arrives.

### Probability of liking

Build logistic/probit models or heuristic formulas to estimate `P(rating >= threshold)`:
```
Features = [
  film_score (Bayesian),
  like_rate,
  favorite_rate,
  high_rating_pct,
  user_similarity_weighted_avg (from neighbors),
  global delta (cohort vs Letterboxd),
  recency (if rating updated recently)
]

P(like) = sigmoid(w · Features)
```

Training data: treat historical user ratings as labels (`1` if user rated ≥3.5, else `0`). Retrain periodically (or online) and log errors to refine weights.

### Advanced filtering integration

- Surfacing predicted probabilities in the advanced search lets you filter by “films I have ≥75% chance to rate ≥4.”
- Provide toggles for “explore outside comfort zone” by picking films with high global score but low `P(like)` for variety.

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
