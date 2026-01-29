export type RankingRow = {
  film_id: number;
  rank: number | null;
  score: number;
  title: string;
  slug: string;
  poster_url: string | null;
  release_year?: number | null;
  watchers: number | null;
  avg_rating: number | null;
  favorite_rate: number | null;
  like_rate: number | null;
  distribution_label: string | null;
  consensus_strength: number | null;
  rating_histogram: Array<{ key: string; label: string; count: number }>;
  directors?: Array<{ id: number; name: string }>;
  genres?: string[];
};
