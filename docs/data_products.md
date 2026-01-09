# Cohort Data Products & Insights

With the ingestion pipeline stabilized (cohort builds, incremental scrapes, and enrichment), we can surface a rich set of outputs that go far beyond a generic “Top 100.” Below is a catalogue of ideas grouped by focus area. Many of these can be composed from existing tables (`ratings`, `cohort_film_stats`, `film_rankings`, `film_histograms`, `ranking_insights`) with a bit of SQL + presentation logic.

---

## Core Rankings

1. **Global Top N lists** — Bayesian-weighted or Wilson-scored rankings limited to the entire cohort. Variants: Top 50/100/250, “Hall of Fame,” “Hidden Gems” (high score, low visibility).
2. **Per-member cohort views** — For each user, recompute rankings using only the subset of the cohort they follow most closely (e.g., “Alex + people Alex follows”). Useful for personalized dashboards.
3. **Temporal slices**
   - **Current year / last 12 months** — Filter `ratings.updated_at` (or `rated_at` where available) to highlight films the cohort is talking about now.
   - **2020s / decade buckets** — Filter `films.release_year`.
   - **Seasonal scrapes** — Compare Summer vs Winter releases or festival seasons.
4. **List intersections** — Re-use `rank subset` logic to intersect cohort rankings with Letterboxd lists (e.g., “Top films from Sight & Sound 2022 according to our cohort”).

## Divergence & Consensus

1. **Cohort vs Letterboxd delta** — Compare cohort average to Letterboxd weighted average and surface:
   - Films cohort champions more than global LB (positive delta).
   - Films cohort dislikes relative to LB (negative delta).
2. **Histogram contrast** — Use stored `film_histograms` to flag titles where the cohort’s rating distribution is skewed vs Letterboxd’s (e.g., “cohort split while LB is unanimous”).
3. **Consensus meter** — Compute standard deviation + interquartile range per film to classify as “Unanimous praise,” “Divisive,” “Mixed.”

## Likes & Engagement

1. **Like-adjusted rankings** — Blend average star rating with like/favorite ratios. Example score:
   ```
   score = z(avg_rating) + α * z(log_watchers) + β * z(like_rate) + γ * z(favorite_rate)
   ```
2. **Likes-only discoveries** — Films with many cohort likes but few ratings (people “liked” the diary entry without rating; these often point to unrated rewatches or special screenings).
3. **Favorite lists** — Aggregate `favorite=True` counts to build a “Cohort Favorites Hall of Fame.”

## People Insights

1. **Top Directors / Actors** — Join `film_people` to the ranking tables. Metrics:
   - Weighted average of their films’ cohort scores.
   - Number of high-ranked films per person within the cohort.
2. **Director/Performer streaks** — Identify creators whose every film sits above the cohort median (latent “always hits” list).
3. **Collaborations** — Pairs of directors/actors valued by the cohort (e.g., “every Scorsese–DiCaprio film ranks in the top 10%”).

## Temporal & Activity Analytics

1. **Recently logged highlights** — Use `ratings.updated_at` to build a daily/weekly digest: “new films discussed by the cohort in the last X days.”
2. **Watch streaks / bursts** — Track how many ratings each member added per week; highlight binge sessions or quiet periods.
3. **Rewatch tracker** — Detect `rated_at` duplicates (if future diary ingestion is re-enabled) to chart which films members return to.

## Segmentation & Smart Buckets

1. **Percentile buckets** — Already implemented in `rank buckets`; expose as segments like “Elite acclaim,” “Cult favorite,” “Crowd pleaser,” “Underrated.”
2. **Engagement clusters** — Use watchers vs rating to categorize films into quadrants and surface them as ready-made smart lists.
3. **Taste clusters** — Compute user similarity (cosine similarity on overlapping ratings) to suggest mini-cohorts or “critics you align with most.”

## Cross-Cohort Comparisons (future-friendly)

1. **Battle of cohorts** — If multiple cohorts exist, compare their top lists, overlaps, and divergences (“What New Yorkers love vs. what Critics Circle loves”).
2. **Overlap heatmaps** — For two cohorts, compute Jaccard similarity of their top N lists to show taste alignment.

## Presentation Ideas

1. **Digest emails / notifications** — Summarize new cohort activity, top movers, new additions to favorites weekly.
2. **Interactive dashboards** — Filter by release year, cohort subset, or ranking strategy with instant recomputes (powered by cached materialized views).
3. **Shareable exports** — Prebuilt CSVs/embeds for “Top 2020s Films,” “Directors we love,” or divergence charts for blogging/social posts.

---

### Implementation Notes

- Most ranking variants can be expressed as SQL views on `cohort_film_stats` + `films` (with additional joins on likes/favorites). For advanced scoring (Bayesian + engagement), consider using materialized `film_rankings` with extra columns for like/favorite z-scores.
- Divergence metrics need a reliable global baseline; we already store Letterboxd aggregates (`letterboxd_rating_count`, `letterboxd_weighted_average`, histograms), so the comparison is straightforward.
- Director/actor rankings require the `film_people` table populated via enrichment. Ensure enrichment runs frequently enough to maintain coverage.
- For time-based slices, index `ratings.updated_at` and `films.release_year` to keep queries fast.

As we continue to capture more metadata (e.g., reintroduce diary feeds or store TMDB genres), we can expand this catalogue with genre-specific lists, location-based stats, or prompts like “Films your cohort scored 5★ but the world ignored.” The key is to reuse the normalized tables the pipeline already maintains while layering thoughtful scoring and storytelling on top.
