export type RankingSortOption = {
  value: string;
  label: string;
  sortBy: "score" | "watchers" | "release_year" | "avg_rating";
  sortOrder: "asc" | "desc";
};

export const DEFAULT_RANKING_SORT: RankingSortOption = {
  value: "score_desc",
  label: "Default ranking score (desc)",
  sortBy: "score",
  sortOrder: "desc",
};

export const RANKING_SORT_OPTIONS: RankingSortOption[] = [
  DEFAULT_RANKING_SORT,
  {
    value: "score_asc",
    label: "Default ranking score (asc)",
    sortBy: "score",
    sortOrder: "asc",
  },
  {
    value: "watchers_desc",
    label: "Watchers (desc)",
    sortBy: "watchers",
    sortOrder: "desc",
  },
  {
    value: "watchers_asc",
    label: "Watchers (asc)",
    sortBy: "watchers",
    sortOrder: "asc",
  },
  {
    value: "release_year_desc",
    label: "Release year (desc)",
    sortBy: "release_year",
    sortOrder: "desc",
  },
  {
    value: "release_year_asc",
    label: "Release year (asc)",
    sortBy: "release_year",
    sortOrder: "asc",
  },
  {
    value: "avg_rating_desc",
    label: "Avg. rating (desc)",
    sortBy: "avg_rating",
    sortOrder: "desc",
  },
  {
    value: "avg_rating_asc",
    label: "Avg. rating (asc)",
    sortBy: "avg_rating",
    sortOrder: "asc",
  },
];
