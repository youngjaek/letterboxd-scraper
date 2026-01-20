import Link from "next/link";
import { ManageCohortPanel } from "@/components/manage-cohort-panel";
import { RankingStrategySelect } from "@/components/ranking-strategy-select";
import { RatingHistogram } from "@/components/rating-histogram";
import { RankingFilters } from "@/components/ranking-filters";
import { PaginationControls } from "@/components/pagination-controls";
import { serverApiBase } from "@/lib/api-base";

const apiBase = serverApiBase;
const defaultStrategy = "bayesian";
type CohortDetail = {
  id: number;
  label: string;
  seed_user_id: number | null;
  seed_username?: string | null;
  member_count: number;
  created_at: string;
  updated_at?: string | null;
  current_task_id?: string | null;
  members: Array<{ username: string; avatar_url: string | null }>;
};

type ScrapeMemberStatus = {
  username: string;
  status: string;
  mode: string;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
};

type ScrapeProgress = {
  status: string;
  run_id: number | null;
  run_type: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  total_members: number;
  completed: number;
  failed: number;
  queued: number;
  in_progress: ScrapeMemberStatus[];
  recent_finished: ScrapeMemberStatus[];
};

type RankingRow = {
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

async function fetchCohort(id: string): Promise<CohortDetail | null> {
  const res = await fetch(`${apiBase}/cohorts/${id}`, { cache: "no-store" });
  if (!res.ok) {
    return null;
  }
  return res.json();
}

const pageSize = 25;

function getParamValues(value: string | string[] | undefined): string[] {
  if (!value) {
    return [];
  }
  return Array.isArray(value) ? value : [value];
}

async function fetchRankings(
  id: string,
  strategy: string,
  searchParams?: Record<string, string | string[] | undefined>,
) {
  const pageParam = searchParams?.page;
  const currentPageRaw = Array.isArray(pageParam) ? pageParam[0] : pageParam;
  const currentPageNum = currentPageRaw ? Math.max(1, parseInt(currentPageRaw, 10) || 1) : 1;
  const query = new URLSearchParams();
  query.set("strategy", strategy);
  query.set("limit", pageSize.toString());
  query.set("page", currentPageNum.toString());
  const multiKeys = ["genres", "countries", "directors"];
  multiKeys.forEach((key) => {
    getParamValues(searchParams?.[key]).forEach((value) => {
      if (value) {
        query.append(key, value);
      }
    });
  });
  const singleKeys = [
    "release_year_min",
    "release_year_max",
    "decade",
  ];
  singleKeys.forEach((key) => {
    const raw = Array.isArray(searchParams?.[key]) ? searchParams?.[key]?.[0] : searchParams?.[key];
    if (raw) {
      query.set(key, raw);
    }
  });
  const url = `${apiBase}/cohorts/${id}/rankings?${query.toString()}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    return { items: [], total: 0, page: currentPageNum };
  }
  const data = await res.json();
  return { ...data, page: currentPageNum };
}

async function fetchScrapeStatus(id: string): Promise<ScrapeProgress | null> {
  const res = await fetch(`${apiBase}/cohorts/${id}/scrape-status`, { cache: "no-store" });
  if (!res.ok) {
    return null;
  }
  return res.json();
}

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "—";
  }
  return `${Math.round(value * 100)}%`;
}

function formatAverage(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "—";
  }
  return value.toFixed(2);
}

function letterboxdUrl(slug: string) {
  return `https://letterboxd.com/film/${slug}/`;
}

function StatPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col rounded-md border border-white/10 bg-black/40 px-3 py-1 text-xs text-white/90">
      <span className="text-[0.55rem] uppercase tracking-[0.3em] text-slate-400">{label}</span>
      <span className="text-sm font-semibold text-white">{value}</span>
    </div>
  );
}

export default async function CohortRankingsPage({
  params,
  searchParams,
}: {
  params: { id: string };
  searchParams?: Record<string, string | string[] | undefined>;
}) {
  const routeParams = params;
  const searchStrategy = searchParams?.strategy;
  const strategy =
    typeof searchStrategy === "string" && searchStrategy.length > 0 ? searchStrategy : defaultStrategy;
  const cohort = await fetchCohort(routeParams.id);
  if (!cohort) {
    return (
      <section className="mx-auto max-w-4xl space-y-4 text-center text-slate-300">
        <p>Cohort {routeParams.id} not found.</p>
        <Link href="/" className="text-brand-primary underline">
          Back to list
        </Link>
      </section>
    );
  }
  const [rankingResponse, scrapeStatus] = await Promise.all([
    fetchRankings(routeParams.id, strategy, searchParams),
    fetchScrapeStatus(routeParams.id),
  ]);
  const rankings: RankingRow[] = rankingResponse.items ?? [];
  const total = rankingResponse.total ?? 0;
  const currentPage = rankingResponse.page ?? 1;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <section className="mx-auto flex max-w-4xl flex-col gap-6">
      <div className="rounded-xl border border-white/10 bg-white/5 p-6 space-y-3">
        <p className="text-xs uppercase tracking-[0.3em] text-brand-accent">Cohort</p>
        <h1 className="text-3xl font-semibold">{cohort.label}</h1>
        <p className="text-sm text-slate-400">
          {cohort.member_count} member(s) · Created {new Date(cohort.created_at).toLocaleDateString()}
        </p>
        <p className="text-sm text-slate-400">
          Last synced {cohort.updated_at ? new Date(cohort.updated_at).toLocaleString() : "never"}
        </p>
        {cohort.seed_username ? (
          <p className="text-sm text-slate-200">
            Seed user{" "}
            <span className="font-semibold text-white">@{cohort.seed_username}</span>
          </p>
        ) : (
          <p className="text-sm text-slate-500">Seed user information unavailable.</p>
        )}
        <Link href="/" className="text-xs text-brand-primary underline">
          ← Back to list
        </Link>
      </div>
      <ManageCohortPanel cohortId={cohort.id} label={cohort.label} currentTaskId={cohort.current_task_id} members={cohort.members} scrapeStatus={scrapeStatus} />
      <div className="rounded-xl border border-white/10 bg-white/5">
        <div className="flex items-center justify-between border-b border-white/10 px-6 py-4 text-xs uppercase tracking-[0.2em] text-slate-400">
          <span>Rankings</span>
          <RankingStrategySelect cohortId={cohort.id} currentStrategy={strategy} />
        </div>
        <RankingFilters />
        {rankings.length === 0 ? (
          <p className="p-6 text-sm text-slate-400">No rankings found for the current filters.</p>
        ) : (
          <>
            <ol>
              {rankings.map((item) => {
                const directorNames = item.directors?.map((director) => director.name).filter(Boolean) ?? [];
                const primaryDirectors = directorNames.slice(0, 2);
                const extraDirectors = Math.max(0, directorNames.length - primaryDirectors.length);
                const genreTags = item.genres ? item.genres.slice(0, 3) : [];
                const metadataLine = item.release_year || primaryDirectors.length > 0;
                return (
                  <li key={item.film_id} className="border-b border-white/5 px-6 py-5 last:border-b-0">
                    <div className="grid gap-4 sm:grid-cols-[120px,1fr]">
                      <div className="max-w-[120px]">
                        <div className="overflow-hidden rounded-lg border border-white/10 bg-black/20">
                          {item.poster_url ? (
                            <img
                              src={item.poster_url}
                              alt={`${item.title} poster`}
                              className="h-full w-full object-cover"
                              loading="lazy"
                            />
                          ) : (
                            <div className="flex aspect-[2/3] items-center justify-center text-xs text-slate-500">
                              No poster
                            </div>
                          )}
                        </div>
                      </div>
                      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_220px] md:items-start">
                        <div className="flex h-full flex-col gap-3">
                        <div className="space-y-1">
                          <p className="text-sm uppercase tracking-[0.3em] text-brand-accent">
                            #{item.rank ?? "?"}
                          </p>
                          <div className="flex flex-wrap items-baseline gap-2">
                            <Link
                              href={letterboxdUrl(item.slug)}
                              target="_blank"
                              className="text-xl font-semibold text-white hover:text-brand-primary"
                            >
                              {item.title}
                            </Link>
                            {metadataLine ? (
                              <span className="text-sm text-slate-300">
                                {item.release_year ? `(${item.release_year})` : ""}
                                {item.release_year && primaryDirectors.length ? " " : ""}
                                {primaryDirectors.length
                                  ? `by ${primaryDirectors.join(", ")}${
                                      extraDirectors > 0 ? ` +${extraDirectors} more` : ""
                                    }`
                                  : ""}
                              </span>
                            ) : null}
                          </div>
                        </div>
                          <p className="text-xs text-slate-500">{item.slug}</p>
                          <div className="min-h-[32px]">
                            {genreTags.length ? (
                              <div className="flex flex-wrap gap-1.5 text-[0.55rem] uppercase tracking-[0.25em] text-slate-400">
                                {genreTags.map((genre) => (
                                  <span
                                    key={genre}
                                    className="rounded-full border border-white/15 px-2 py-0.5 text-slate-200/80"
                                  >
                                    {genre}
                                  </span>
                                ))}
                              </div>
                            ) : (
                              <div className="h-4" aria-hidden="true" />
                            )}
                          </div>
                        <div className="mt-auto flex flex-wrap items-end gap-3">
                          <StatPill label="Watchers" value={item.watchers?.toLocaleString() ?? "—"} />
                          <StatPill label="Avg" value={formatAverage(item.avg_rating)} />
                          <StatPill label="Fav %" value={formatPercent(item.favorite_rate)} />
                          <StatPill label="Like %" value={formatPercent(item.like_rate)} />
                          <StatPill
                              label="Consensus"
                              value={
                                item.consensus_strength !== null && item.consensus_strength !== undefined
                                  ? item.consensus_strength.toFixed(2)
                                  : "—"
                              }
                            />
                          </div>
                        </div>
                        <div className="flex h-full flex-col">
                          <div className="text-right text-xs uppercase text-slate-400">
                            <p className="font-semibold text-white">
                              Score <span className="text-brand-primary">{item.score.toFixed(3)}</span>
                            </p>
                            <p>Distribution {item.distribution_label ?? "mixed"}</p>
                          </div>
                          <div className="mt-auto w-full rounded-lg border border-white/10 bg-black/30 px-2 py-1">
                            {item.rating_histogram?.length ? (
                              <RatingHistogram bins={item.rating_histogram} watchers={item.watchers} />
                            ) : (
                              <div className="text-center text-[0.6rem] text-slate-500">No data</div>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>
            <PaginationControls page={currentPage} totalPages={totalPages} />
          </>
        )}
      </div>
    </section>
  );
}
