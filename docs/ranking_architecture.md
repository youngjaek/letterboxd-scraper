# Ranking & Insights Architecture

This document explains how ranking results and the new percentile-based “smart buckets” are generated, persisted, and consumed inside the Letterboxd cohort scraper. Use it as a reference when extending ranking strategies, building exports, or wiring a UI/dashboard on top of the stored data.

## Data Building Blocks

| Artifact | Source | Purpose |
| --- | --- | --- |
| `ratings` | Scrapers (`scrape` with optional `--full`) | Raw rating rows for each cohort member. |
| `cohort_members` | Follow graph scraper | Defines which users belong to each cohort. |
| `cohort_film_stats` (materialized view) | `stats refresh` | Cohort-level aggregates (watchers, average rating, first/last rating timestamps). This is the standard input for both ranking and bucket computations. |
| `film_rankings` | `rank compute` | Canonical ranking snapshot for each `(cohort_id, strategy)` pair. Stores rank, score, and strategy parameters. |
| `ranking_insights` | `rank buckets --persist` | Derived metadata (percentiles, z-scores, cluster/bucket labels, filters/timeframe keys) for each film per cohort + strategy + timeframe. Enables reusing a previously computed slice without recomputing. |

## Ranking Pipeline

1. **Refresh stats**  
   `letterboxd-scraper stats refresh` rebuilds the `cohort_film_stats` materialized view so it reflects the latest ratings.

2. **Compute strategy scores**  
   `letterboxd-scraper rank compute <cohort_id> --strategy bayesian` runs `services.rankings.compute_bayesian`, which:
   - Pulls `watchers` and `avg_rating` from `cohort_film_stats`.
   - Computes a Bayesian weighted score per film using the configured `m_value`:  
     `score = (watchers / (watchers + m)) * avg_rating + (m / (watchers + m)) * cohort_avg`.
   - Orders films by score and assigns rank positions.

3. **Persist canonical rows**  
   `services.rankings.persist_rankings` wipes existing rows for that `(cohort_id, strategy)` and inserts the new results into `film_rankings`, including the strategy parameters (`params` JSON) and `computed_at` timestamp. All other features and exports consume the ranks from this table.

### Cohort Affinity scoring (Phase 3 default)

The Phase 3 UI uses a richer “cohort_affinity” strategy that balances popularity, sentiment, and enthusiasm signals instead of relying solely on Bayesian means:

- **Inputs** come from the refreshed `cohort_film_stats` view (watchers, avg rating, high/low rating percentages, histogram buckets) plus per-film like/favourite counts.
- **Normalized features** are z-scored within the cohort so no single metric dominates:
  - `avg_rating_z`
  - `log_watchers_z` (log₁₀ dampens runaway blockbusters; capped at `<=1.0`)
  - `favorite_rate_z` (`favorites/watchers`) and `like_rate_z`
  - `consensus_strength = high_rating_pct - low_rating_pct`
  - `distribution_bonus` derived from histogram shape labels (e.g., strong-left, bimodal).
- **Weights** (tuned empirically):
  ```
  score =
      0.35 * avg_rating_z
    + 0.20 * log_watchers_z
    + 0.25 * favorite_rate_z
    + 0.10 * like_rate_z
    + 0.10 * distribution_bonus
    + 0.10 * consensus_strength
  ```
  - `distribution_bonus` = +0.30 for strongly left-skewed (majority 4½–5★), +0.15 for left-skewed, 0 for balanced, negative for right-skewed/polarized under-performers.
  - `consensus_strength` ensures elite-but-smaller films (high ≥4★ share, low ≤2★ share) beat merely “okay but popular” entries.
- **Filters** (coming after the strategy rollout) will let the UI slice by watchers bands (“obscure gems”), distribution labels (bimodal, strong-left, etc.), and favourite percentages without changing the canonical ranking rows.

Persisted rows set `strategy='cohort_affinity'` so the API/UI can request them via `?strategy=cohort_affinity`.

4. **Consumption**  
   - `rank subset` joins `film_rankings` with Letterboxd list/filmography slugs to show how a curated list fares within the cohort.
   - `export csv` emits the ranking snapshot to a CSV with titles, slugs, watchers, and average ratings.
   - Custom SQL, dashboards, or APIs can read `film_rankings` directly since it holds the authoritative scores/ranks.

## Bucket & Cluster Insights

The `rank buckets` command focuses on surfacing interesting clusters without manually picking score/watch count ranges.

1. **Input data**  
   Buckets always read from `cohort_film_stats` (they do *not* require `film_rankings`, although in practice you’ll refresh both so the underlying stats are current). Optional filters are applied before deriving metrics:
   - `--release-start / --release-end`
   - `--watched-year`
   - `--watched-since / --watched-until`
   - `--recent-years N` (shortcut for a rolling window)

2. **Percentiles & z-scores**  
   `services.insights.compute_ranking_buckets`:
   - Calculates percentile ranks for watchers and average rating (ties receive the midpoint percentile for their block).
   - Computes z-scores for watchers/avg rating to understand how far each film deviates from the cohort mean.

3. **Human-friendly labels**  
   - **Bucket labels** (e.g., “Elite acclaim,” “Cult favorite,” “Crowd pleaser”) are derived from percentile thresholds so they automatically adapt to the cohort distribution.
   - **Cluster labels** (e.g., “High rating / low watchers,” “High engagement / mixed sentiment”) are driven by z-score combinations. These help highlight engagement vs. sentiment trade-offs.

4. **Persistence & reuse**  
   - Running `rank buckets ... --persist` stores every row in `ranking_insights`, keyed by `(cohort_id, strategy, film_id, timeframe_key)`. The timeframe key is derived from the filters (e.g., `release:2000-2010|watched-year:2024` or `watched:2023-08-01-2024-07-31`).
   - `rank buckets ... --load <timeframe_key>` rehydrates a saved slice instantly, skipping recomputation. This is useful for CLI exports, future dashboards, or sharing “smart lists” with collaborators.

5. **Output & downstream use**  
   The CLI prints:
   - A summary table showing bucket sizes and dominant cluster labels.
   - Top films per bucket with watchers, avg rating, percentile scores, and cluster labels.
   Stored insights can also back a UI (e.g., scatter plots, cards) without hitting the raw stats view.

## Typical Workflow

1. `cohort build` / `cohort refresh` – define membership.
2. `scrape` (with or without `--full`) – keep `ratings` current.
3. `stats refresh` – rebuild `cohort_film_stats`.
4. `rank compute` – populate `film_rankings`.
5. `rank buckets --persist` – generate percentile/cluster slices for temporal windows or release eras.
6. `rank subset` / `export csv` / custom dashboards – consume the stored ranking data or bucket insights.

## Extensibility Notes

- **New strategies**: implement `compute_<strategy>` in `services.rankings`, persist via `persist_rankings`, and expose it through the CLI. All downstream tools automatically gain access once the rows exist in `film_rankings`.
- **Alternate bucket logic**: `services.insights` is designed for extension—swap in k-means clustering, additional metrics (e.g., variance, recency decay), or new labels without touching the CLI contract.
- **Dashboards/UIs**: both `film_rankings` and `ranking_insights` include enough metadata (params, filters, computed timestamps) to render history or compare slices. Consider building a Streamlit/Panel dashboard that reads those tables directly if you need richer visualization.
