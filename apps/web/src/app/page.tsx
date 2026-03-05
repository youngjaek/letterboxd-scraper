import { CreateCohortForm } from "@/components/create-cohort-form";
import Link from "next/link";
import { serverApiBase } from "@/lib/api-base";
import { DemoBanner } from "@/components/demo-banner";
import { cacheResult } from "@/lib/server-cache";
import { isDemoMode } from "@/lib/demo-flags";

const apiBase = serverApiBase;

type CohortSummary = {
  id: number;
  label: string;
  member_count: number;
  created_at: string;
};

type RankingItem = {
  film_id: number;
  rank: number | null;
  score: number;
  title: string;
  slug: string;
  release_year?: number | null;
  watchers: number | null;
  avg_rating: number | null;
  rating_histogram?: Array<{ key: string; label: string; count: number }>;
  directors?: Array<{ id: number; name: string }>;
  genres?: string[];
};

type RankingResponse = {
  items: RankingItem[];
  total: number;
};

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

async function fetchRankings(cohortId: number, limit = 10): Promise<RankingResponse> {
  const request = async () => {
    const res = await fetch(`${apiBase}/cohorts/${cohortId}/rankings?limit=${limit}`, {
      cache: "no-store",
    });
    if (!res.ok) {
      console.warn("Failed to load rankings", res.status, await res.text());
      return { items: [], total: 0 };
    }
    return res.json();
  };
  if (!shouldCacheApi) {
    return request();
  }
  const cacheKey = `rankings:home:${cohortId}:limit=${limit}`;
  return cacheResult(cacheKey, DEMO_CACHE_TTL_MS, request);
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
  const featuredCohort = cohorts[0];
  const rankingResponse = featuredCohort ? await fetchRankings(featuredCohort.id) : { items: [], total: 0 };
  const rankings = rankingResponse.items;
  return (
    <section className="mx-auto flex max-w-5xl flex-col gap-10">
      <DemoBanner />
      <header className="space-y-4">
        <p className="text-sm uppercase tracking-[0.3em] text-brand-accent">Live Cohort Briefing</p>
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
            {cohorts.length === 0 ? (
              <p className="p-6 text-sm text-slate-400">No cohorts found; create one via the CLI or API.</p>
            ) : (
              <ul>
                {cohorts.map((cohort) => (
                <li key={cohort.id} className="border-b border-white/5 px-6 py-4 last:border-b-0">
                  <Link href={`/cohorts/${cohort.id}`} className="flex items-center justify-between">
                    <div>
                      <p className="text-lg font-medium text-brand-primary">{cohort.label}</p>
                      <p className="text-xs text-slate-400">ID {cohort.id} · Created {new Date(cohort.created_at).toLocaleDateString()}</p>
                    </div>
                    <div className="text-right text-sm text-slate-200">
                      <p>{cohort.member_count} member(s)</p>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
            )}
          </div>
        </div>
        <div>
          <CreateCohortForm />
          {featuredCohort && (
            <div className="mt-6 rounded-xl border border-white/10 bg-white/5 p-6">
              <h3 className="text-lg font-semibold text-brand-primary">
                Top picks · {featuredCohort.label}
              </h3>
              {rankings.length === 0 ? (
                <p className="mt-2 text-sm text-slate-400">No rankings yet.</p>
              ) : (
                <ol className="mt-4 space-y-3">
                  {rankings.map((item) => (
                    <li key={item.film_id} className="flex items-center justify-between text-sm">
                      <div>
                        <span className="mr-3 text-xs text-slate-500">#{item.rank ?? "?"}</span>
                        <span className="font-medium text-white">{item.title}</span>
                      </div>
                      <div className="text-right text-slate-400">
                        <p>{item.avg_rating?.toFixed(2) ?? "--"} avg</p>
                        <p className="text-xs">{item.watchers ?? 0} watchers</p>
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          )}
        </div>
      </div>
      <footer className="text-sm text-slate-400">
        Backend running? Start everything with
        <code className="mx-2 rounded bg-black/40 px-2 py-1 text-xs">
          docker compose -f docker-compose.dev.yml up --build
        </code>
        (API on 8000, web on 3000) or point `NEXT_PUBLIC_API_BASE_URL` at a manually started FastAPI server.
      </footer>
    </section>
  );
}
