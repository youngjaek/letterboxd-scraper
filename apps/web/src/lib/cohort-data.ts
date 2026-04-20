import { serverApiBase } from "@/lib/api-base";
import { isDemoMode } from "@/lib/demo-flags";
import { cacheResult } from "@/lib/server-cache";
import type { CohortSummary } from "@/types/cohort";
import type { RankingRow } from "@/types/ranking-row";

const apiBase = serverApiBase;

const DEMO_ALLOWED_HANDLES = ["thebigal", "filipe"];
const DEMO_BLOCKED_IDS = new Set<number>([5, 6]);

const shouldCacheApi = isDemoMode || process.env.NODE_ENV === "production";
const COHORT_LIST_TTL_MS = isDemoMode ? 30_000 : 60_000;
const PREVIEW_TTL_MS = isDemoMode ? 30_000 : 120_000;

export type CohortCardData = {
  cohort: CohortSummary;
  preview: RankingRow[];
  descriptor: string;
  freshnessLabel: string;
  statusLabel: string;
  searchText: string;
};

async function requestJson<T>(url: string): Promise<T | null> {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    return null;
  }
  return res.json();
}

export async function fetchCohorts(): Promise<CohortSummary[]> {
  const request = async () => {
    const data = await requestJson<CohortSummary[]>(`${apiBase}/cohorts`);
    return data ?? [];
  };
  if (!shouldCacheApi) {
    return request();
  }
  return cacheResult("cohorts:list", COHORT_LIST_TTL_MS, request);
}

export function curateVisibleCohorts(cohorts: CohortSummary[]): CohortSummary[] {
  if (!isDemoMode) {
    return cohorts;
  }
  return cohorts.filter((cohort) => {
    if (DEMO_BLOCKED_IDS.has(cohort.id)) {
      return false;
    }
    const normalizedLabel = cohort.label.toLowerCase();
    const normalizedSeed = cohort.seed_username?.toLowerCase() ?? "";
    return DEMO_ALLOWED_HANDLES.some(
      (handle) => normalizedLabel.includes(handle) || normalizedSeed.includes(handle),
    );
  });
}

export async function fetchVisibleCohorts(): Promise<CohortSummary[]> {
  const cohorts = await fetchCohorts();
  return curateVisibleCohorts(cohorts);
}

export async function fetchRankingPreview(cohortId: number, limit = 4): Promise<RankingRow[]> {
  const request = async () => {
    const query = new URLSearchParams({
      strategy: "bayesian",
      limit: String(limit),
      page: "1",
      result_limit: String(limit),
    });
    const data = await requestJson<{ items?: RankingRow[] }>(
      `${apiBase}/cohorts/${cohortId}/rankings?${query.toString()}`,
    );
    return data?.items ?? [];
  };
  if (!shouldCacheApi) {
    return request();
  }
  return cacheResult(`cohort:${cohortId}:preview:${limit}`, PREVIEW_TTL_MS, request);
}

function daysSince(value?: string | null): number | null {
  if (!value) {
    return null;
  }
  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) {
    return null;
  }
  return Math.max(0, Math.floor((Date.now() - timestamp) / 86_400_000));
}

export function formatShortDate(value?: string | null): string {
  if (!value) {
    return "Unknown";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Unknown";
  }
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(date);
}

export function formatFreshness(updatedAt?: string | null, createdAt?: string | null): string {
  const source = updatedAt ?? createdAt;
  const days = daysSince(source);
  if (days === null) {
    return "Unknown";
  }
  if (days === 0) {
    return "Updated today";
  }
  if (days === 1) {
    return "Updated yesterday";
  }
  if (days <= 7) {
    return `${days}d ago`;
  }
  if (days <= 30) {
    return `${Math.floor(days / 7)}w ago`;
  }
  return formatShortDate(source);
}

function buildDescriptor(cohort: CohortSummary, preview: RankingRow[]): string {
  if (cohort.seed_username) {
    return `Friends' canon for @${cohort.seed_username}`;
  }
  if (preview[0]?.title) {
    return `Includes ${preview[0].title}`;
  }
  return "Open canon";
}

function buildStatusLabel(cohort: CohortSummary): string {
  const days = daysSince(cohort.updated_at ?? cohort.created_at);
  if (days === null) {
    return "Ready";
  }
  if (days <= 7) {
    return "Fresh";
  }
  return "Saved";
}

function buildSearchText(cohort: CohortSummary, preview: RankingRow[]): string {
  const previewTitles = preview.map((film) => film.title).join(" ");
  return [
    cohort.label,
    cohort.seed_username ?? "",
    previewTitles,
    cohort.member_count.toString(),
  ]
    .join(" ")
    .toLowerCase();
}

export async function buildCohortCards(
  cohorts: CohortSummary[],
  limit = 6,
  previewSize = 3,
): Promise<CohortCardData[]> {
  const slice = cohorts.slice(0, limit);
  const previews = await Promise.all(slice.map((cohort) => fetchRankingPreview(cohort.id, previewSize)));
  return slice.map((cohort, index) => {
    const preview = previews[index] ?? [];
    return {
      cohort,
      preview,
      descriptor: buildDescriptor(cohort, preview),
      freshnessLabel: formatFreshness(cohort.updated_at, cohort.created_at),
      statusLabel: buildStatusLabel(cohort),
      searchText: buildSearchText(cohort, preview),
    };
  });
}

export function filterCohortCards(cards: CohortCardData[], query: string): CohortCardData[] {
  const normalized = query.trim().toLowerCase();
  if (!normalized) {
    return cards;
  }
  return cards.filter((card) => card.searchText.includes(normalized));
}
