import Link from "next/link";
import { Suspense } from "react";
import { ManageCohortPanel } from "@/components/manage-cohort-panel";
import { RankingStrategySelect } from "@/components/ranking-strategy-select";
import { RankingFilters } from "@/components/ranking-filters";
import { SearchParamsProvider } from "@/components/search-params-provider";
import { RankingBrowser } from "@/components/ranking-browser";
import { serverApiBase } from "@/lib/api-base";
import { formatFreshness, formatShortDate } from "@/lib/cohort-data";
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
      <section className="mx-auto flex w-full max-w-4xl flex-col items-center gap-4 py-16 text-center">
        <p className="eyebrow">Not found</p>
        <h1 className="section-title">That cohort is not available.</h1>
        <Link href="/cohorts" className="button-secondary">
          Back to cohorts
        </Link>
      </section>
    );
  }

  const scrapeStatus = await scrapeStatusPromise;
  const currentStageLabel = cohort.current_task_stage ?? "ready";

  return (
    <section className="mx-auto flex w-full max-w-6xl flex-col gap-6 pb-12">
      <DemoBanner />

      <header className="panel grid gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(18rem,0.85fr)]">
        <div className="space-y-4">
          <Link href="/cohorts" className="button-ghost px-4 py-2 text-xs">
            Back to cohorts
          </Link>
          <div className="space-y-3">
            <p className="eyebrow">Cohort profile</p>
            <h1 className="section-title">{cohort.label}</h1>
            <p className="text-sm leading-7 text-[color:var(--text-muted)] sm:text-base">
              A living ranking board for {cohort.member_count} members. Use the explorer below to inspect consensus,
              hidden favorites, and how the room shifts over time.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <span className="status-chip">{cohort.member_count} members</span>
            <span className="status-chip">{formatFreshness(cohort.updated_at, cohort.created_at)}</span>
            {cohort.seed_username ? <span className="status-chip">@{cohort.seed_username}</span> : null}
          </div>
        </div>

        <div className="panel-soft grid gap-4 sm:grid-cols-2">
          <div>
            <p className="field-label">Created</p>
            <p className="mt-2 text-lg font-semibold text-[color:var(--text-strong)]">
              {formatShortDate(cohort.created_at)}
            </p>
          </div>
          <div>
            <p className="field-label">Last synced</p>
            <p className="mt-2 text-lg font-semibold text-[color:var(--text-strong)]">
              {cohort.updated_at ? formatShortDate(cohort.updated_at) : "Never"}
            </p>
          </div>
          <div>
            <p className="field-label">Current stage</p>
            <p className="mt-2 text-lg font-semibold capitalize text-[color:var(--text-strong)]">
              {currentStageLabel.replaceAll("_", " ")}
            </p>
          </div>
          <div>
            <p className="field-label">Seed profile</p>
            <p className="mt-2 text-lg font-semibold text-[color:var(--text-strong)]">
              {cohort.seed_username ? `@${cohort.seed_username}` : "Unavailable"}
            </p>
          </div>
        </div>
      </header>

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
      <div className="panel overflow-hidden">
        <div className="flex flex-col gap-4 border-b border-white/10 pb-5 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="eyebrow">Rankings explorer</p>
            <h2 className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">Read the room, title by title.</h2>
          </div>
          <RankingStrategySelect cohortId={cohortId} currentStrategy={strategy} />
        </div>
        <div className="pt-5">
          <RankingFilters />
        </div>
        <div className="pt-5">
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
      </div>
    </SearchParamsProvider>
  );
}

function RankingPanelFallback() {
  return (
    <div className="panel animate-pulse">
      <div className="flex items-center justify-between border-b border-white/10 pb-5">
        <div className="space-y-2">
          <div className="h-3 w-24 rounded-full bg-white/10" />
          <div className="h-8 w-56 rounded-full bg-white/10" />
        </div>
        <div className="h-10 w-44 rounded-full bg-white/10" />
      </div>
      <div className="space-y-4 py-6">
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
