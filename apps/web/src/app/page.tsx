import { CreateCohortForm } from "@/components/create-cohort-form";
import { serverApiBase } from "@/lib/api-base";
import { DemoBanner } from "@/components/demo-banner";
import { cacheResult } from "@/lib/server-cache";
import { isDemoMode } from "@/lib/demo-flags";
import { CohortList } from "@/components/cohort-list";
import type { CohortSummary } from "@/types/cohort";

const apiBase = serverApiBase;

const DEMO_ALLOWED_HANDLES = ["thebigal", "filipe"];
const DEMO_BLOCKED_IDS = new Set<number>([5, 6]);

const shouldCacheApi = isDemoMode;
const DEMO_CACHE_TTL_MS = 30_000;

async function fetchCohorts(): Promise<CohortSummary[]> {
  const request = async () => {
    const res = await fetch(`${apiBase}/cohorts`, { cache: "no-store" });
    if (!res.ok) {
      console.warn("Failed to load cohorts", res.status, await res.text());
      return [];
    }
    return res.json();
  };
  if (!shouldCacheApi) {
    return request();
  }
  return cacheResult("cohorts:list", DEMO_CACHE_TTL_MS, request);
}

function curateDemoCohorts(cohorts: CohortSummary[]): CohortSummary[] {
  return cohorts.filter((cohort) => {
    if (DEMO_BLOCKED_IDS.has(cohort.id)) {
      return false;
    }
    const normalizedLabel = cohort.label.toLowerCase();
    return DEMO_ALLOWED_HANDLES.some((handle) => normalizedLabel.includes(handle));
  });
}

export default async function Home() {
  const allCohorts = await fetchCohorts();
  const cohorts = isDemoMode ? curateDemoCohorts(allCohorts) : allCohorts;
  return (
    <section className="mx-auto flex max-w-5xl flex-col gap-10">
      <DemoBanner />
      <header className="space-y-4">
        <h1 className="text-4xl font-semibold">Kinoboxd</h1>
        <p className="text-base text-slate-300">
          Curated Letterboxd cohorts with fresh rankings, sentiment, and watchers—ready for stakeholders to explore.
        </p>
      </header>
      <div className="grid gap-6 md:grid-cols-[2fr,1fr]">
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-2xl font-semibold">Cohorts</h2>
            <span className="text-sm text-slate-400">{cohorts.length} total</span>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/5">
            <CohortList cohorts={cohorts} />
          </div>
        </div>
        <div>
          <CreateCohortForm />
        </div>
      </div>
    </section>
  );
}
