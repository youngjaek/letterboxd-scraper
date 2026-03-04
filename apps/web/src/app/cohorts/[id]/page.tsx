import Link from "next/link";
import { ManageCohortPanel } from "@/components/manage-cohort-panel";
import { RankingStrategySelect } from "@/components/ranking-strategy-select";
import { RankingFilters } from "@/components/ranking-filters";
import { SearchParamsProvider } from "@/components/search-params-provider";
import { RankingBrowser } from "@/components/ranking-browser";
import { serverApiBase } from "@/lib/api-base";
import { parsePageSize, parseResultLimit } from "@/lib/ranking-options";
import { RankingRow } from "@/types/ranking-row";
import { DemoBanner } from "@/components/demo-banner";

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

async function fetchCohort(id: string): Promise<CohortDetail | null> {
  const res = await fetch(`${apiBase}/cohorts/${id}`, { cache: "no-store" });
  if (!res.ok) {
    return null;
  }
  return res.json();
}

function getParamValues(value: string | string[] | undefined): string[] {
  if (!value) {
    return [];
  }
  return Array.isArray(value) ? value : [value];
}

function serializeSearchParamsForProvider(params?: Record<string, string | string[] | undefined>): string {
  const query = new URLSearchParams();
  if (!params) {
    return "";
  }
  Object.entries(params).forEach(([key, rawValue]) => {
    if (Array.isArray(rawValue)) {
      rawValue.forEach((entry) => {
        if (entry) {
          query.append(key, entry);
        }
      });
    } else if (rawValue) {
      query.set(key, rawValue);
    }
  });
  return query.toString();
}

function parsePage(value: string | string[] | undefined): number {
  const raw = Array.isArray(value) ? value[0] : value;
  if (!raw) {
    return 1;
  }
  const parsed = parseInt(raw, 10);
  if (Number.isNaN(parsed) || parsed < 1) {
    return 1;
  }
  return parsed;
}

async function fetchRankings(
  id: string,
  strategy: string,
  searchParams: Record<string, string | string[] | undefined> | undefined,
  resultLimit: number,
) {
  const query = new URLSearchParams();
  query.set("strategy", strategy);
  query.set("limit", resultLimit.toString());
  query.set("page", "1");
  query.set("result_limit", resultLimit.toString());
  const multiKeys = ["genres", "countries", "directors"];
  multiKeys.forEach((key) => {
    getParamValues(searchParams?.[key]).forEach((value) => {
      if (value) {
        query.append(key, value);
      }
    });
  });
  const singleKeys = [
    "distribution",
    "release_year_min",
    "release_year_max",
    "decade",
    "watchers_min",
    "watchers_max",
    "letterboxd_source",
  ];
  singleKeys.forEach((key) => {
    const raw = Array.isArray(searchParams?.[key]) ? searchParams?.[key]?.[0] : searchParams?.[key];
    if (typeof raw === "string" && raw.length > 0) {
      query.set(key, raw);
    }
  });
  const url = `${apiBase}/cohorts/${id}/rankings?${query.toString()}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    return { items: [], total: 0 };
  }
  return res.json();
}

async function fetchScrapeStatus(id: string): Promise<ScrapeProgress | null> {
  const res = await fetch(`${apiBase}/cohorts/${id}/scrape-status`, { cache: "no-store" });
  if (!res.ok) {
    return null;
  }
  return res.json();
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
  const selectedPageSize = parsePageSize(searchParams?.limit);
  const selectedResultLimit = parseResultLimit(searchParams?.result_limit);
  const currentPage = parsePage(searchParams?.page);
  const sortByParam = Array.isArray(searchParams?.sort_by) ? searchParams?.sort_by[0] : searchParams?.sort_by;
  const sortOrderParam = Array.isArray(searchParams?.sort_order)
    ? searchParams?.sort_order[0]
    : searchParams?.sort_order;
  const initialQueryString = serializeSearchParamsForProvider(searchParams);
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
    fetchRankings(routeParams.id, strategy, searchParams, selectedResultLimit),
    fetchScrapeStatus(routeParams.id),
  ]);
  const rankings: RankingRow[] = rankingResponse.items ?? [];
  const total = rankingResponse.total ?? rankings.length;
  return (
    <section className="mx-auto flex max-w-4xl flex-col gap-6">
      <DemoBanner />
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
      <SearchParamsProvider initialQueryString={initialQueryString}>
        <div className="rounded-xl border border-white/10 bg-white/5">
          <div className="flex items-center justify-between border-b border-white/10 px-6 py-4 text-xs uppercase tracking-[0.2em] text-slate-400">
            <span>Rankings</span>
            <RankingStrategySelect cohortId={cohort.id} currentStrategy={strategy} />
          </div>
          <RankingFilters />
          <RankingBrowser
            items={rankings}
            totalItems={total}
            initialPage={currentPage}
            initialPageSize={selectedPageSize}
            initialResultLimit={selectedResultLimit}
            initialSortBy={sortByParam}
            initialSortOrder={sortOrderParam}
          />
        </div>
      </SearchParamsProvider>
    </section>
  );
}
