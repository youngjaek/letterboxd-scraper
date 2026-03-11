import Link from "next/link";
import { Suspense } from "react";
import { ManageCohortPanel } from "@/components/manage-cohort-panel";
import { RankingStrategySelect } from "@/components/ranking-strategy-select";
import { RankingFilters } from "@/components/ranking-filters";
import { SearchParamsProvider } from "@/components/search-params-provider";
import { RankingBrowser } from "@/components/ranking-browser";
import { serverApiBase } from "@/lib/api-base";
import { parsePageSize, parseResultLimit } from "@/lib/ranking-options";
import { RankingRow } from "@/types/ranking-row";
import { DemoBanner } from "@/components/demo-banner";
import { cacheResult } from "@/lib/server-cache";
import { isDemoMode } from "@/lib/demo-flags";
import type { CohortDetail } from "@/types/cohort";

const apiBase = serverApiBase;
const defaultStrategy = "bayesian";
const shouldCacheHeavyData = isDemoMode || process.env.NODE_ENV === "production";
const HEAVY_DATA_CACHE_TTL_MS = isDemoMode ? 30_000 : 60_000;
const shouldCacheScrapeStatus = isDemoMode;
const SCRAPE_STATUS_CACHE_TTL_MS = 15_000;

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
  current_stage?: string | null;
};

async function fetchCohort(id: string): Promise<CohortDetail | null> {
  const request = async () => {
    const res = await fetch(`${apiBase}/cohorts/${id}`, { cache: "no-store" });
    if (!res.ok) {
      return null;
    }
    return res.json();
  };
  if (!shouldCacheHeavyData) {
    return request();
  }
  return cacheResult(`cohort:${id}`, HEAVY_DATA_CACHE_TTL_MS, request);
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
  const request = async () => {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) {
      return { items: [], total: 0 };
    }
    return res.json();
  };
  if (!shouldCacheHeavyData) {
    return request();
  }
  return cacheResult(`cohort:${id}:rankings:${query.toString()}`, HEAVY_DATA_CACHE_TTL_MS, request);
}

async function fetchScrapeStatus(id: string): Promise<ScrapeProgress | null> {
  const request = async () => {
    const res = await fetch(`${apiBase}/cohorts/${id}/scrape-status`, { cache: "no-store" });
    if (!res.ok) {
      return null;
    }
    return res.json();
  };
  if (!shouldCacheScrapeStatus) {
    return request();
  }
  return cacheResult(`cohort:${id}:scrape-status`, SCRAPE_STATUS_CACHE_TTL_MS, request);
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
  const scrapeStatusPromise = fetchScrapeStatus(routeParams.id);
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
  const scrapeStatus = await scrapeStatusPromise;
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
      <ManageCohortPanel
        cohortId={cohort.id}
        label={cohort.label}
        currentTaskId={cohort.current_task_id}
        currentTaskStage={cohort.current_task_stage}
        members={cohort.members}
        scrapeStatus={scrapeStatus}
      />
      <Suspense fallback={<RankingPanelFallback />}>
        <RankingSection
          cohortId={cohort.id}
          routeId={routeParams.id}
          strategy={strategy}
          searchParams={searchParams}
          selectedPageSize={selectedPageSize}
          selectedResultLimit={selectedResultLimit}
          currentPage={currentPage}
          sortByParam={sortByParam}
          sortOrderParam={sortOrderParam}
          initialQueryString={initialQueryString}
        />
      </Suspense>
    </section>
  );
}

type RankingSectionProps = {
  cohortId: number;
  routeId: string;
  strategy: string;
  searchParams?: Record<string, string | string[] | undefined>;
  selectedPageSize: number;
  selectedResultLimit: number;
  currentPage: number;
  sortByParam?: string;
  sortOrderParam?: string;
  initialQueryString: string;
};

async function RankingSection({
  cohortId,
  routeId,
  strategy,
  searchParams,
  selectedPageSize,
  selectedResultLimit,
  currentPage,
  sortByParam,
  sortOrderParam,
  initialQueryString,
}: RankingSectionProps) {
  const rankingResponse = await fetchRankings(routeId, strategy, searchParams, selectedResultLimit);
  const rankings: RankingRow[] = rankingResponse.items ?? [];
  const total = rankingResponse.total ?? rankings.length;
  return (
    <SearchParamsProvider initialQueryString={initialQueryString}>
      <div className="rounded-xl border border-white/10 bg-white/5">
        <div className="flex items-center justify-between border-b border-white/10 px-6 py-4 text-xs uppercase tracking-[0.2em] text-slate-400">
          <span>Rankings</span>
          <RankingStrategySelect cohortId={cohortId} currentStrategy={strategy} />
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
  );
}

function RankingPanelFallback() {
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 animate-pulse">
      <div className="flex items-center justify-between border-b border-white/10 px-6 py-4">
        <div className="h-4 w-24 rounded-full bg-white/10" />
        <div className="h-8 w-40 rounded-full bg-white/10" />
      </div>
      <div className="border-b border-white/10 px-6 py-4">
        <div className="h-6 w-32 rounded-full bg-white/10" />
      </div>
      <div className="space-y-4 px-6 py-6">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="flex items-center justify-between border-b border-white/10 pb-4 last:border-none last:pb-0">
            <div className="h-4 w-1/2 rounded-full bg-white/10" />
            <div className="flex flex-col items-end gap-2">
              <div className="h-3 w-16 rounded-full bg-white/10" />
              <div className="h-3 w-24 rounded-full bg-white/10" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
