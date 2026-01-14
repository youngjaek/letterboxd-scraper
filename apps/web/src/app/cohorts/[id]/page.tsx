import Link from "next/link";
import { CohortActions } from "@/components/cohort-actions";
import { RankingStrategySelect } from "@/components/ranking-strategy-select";

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const defaultStrategy = "cohort_affinity";

type RankingRow = {
  film_id: number;
  rank: number | null;
  score: number;
  title: string;
  slug: string;
  watchers: number | null;
  avg_rating: number | null;
  favorite_rate: number | null;
  like_rate: number | null;
  distribution_label: string | null;
  consensus_strength: number | null;
};

async function fetchCohort(id: string) {
  const res = await fetch(`${apiBase}/cohorts/${id}`, { cache: "no-store" });
  if (!res.ok) {
    return null;
  }
  return res.json();
}

async function fetchRankings(id: string, strategy: string) {
  const url = `${apiBase}/cohorts/${id}/rankings?limit=50&strategy=${encodeURIComponent(strategy)}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    return [];
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

export default async function CohortRankingsPage({
  params,
  searchParams,
}: {
  params: { id: string };
  searchParams?: Record<string, string | string[] | undefined>;
}) {
  const searchStrategy = searchParams?.strategy;
  const strategy =
    typeof searchStrategy === "string" && searchStrategy.length > 0 ? searchStrategy : defaultStrategy;
  const cohort = await fetchCohort(params.id);
  if (!cohort) {
    return (
      <section className="mx-auto max-w-4xl space-y-4 text-center text-slate-300">
        <p>Cohort {params.id} not found.</p>
        <Link href="/" className="text-brand-primary underline">
          Back to list
        </Link>
      </section>
    );
  }
  const rankings: RankingRow[] = await fetchRankings(params.id, strategy);
  return (
    <section className="mx-auto flex max-w-4xl flex-col gap-6">
      <div>
        <p className="text-xs uppercase tracking-[0.3em] text-brand-accent">Cohort</p>
        <h1 className="text-3xl font-semibold">{cohort.label}</h1>
        <p className="text-sm text-slate-400">{cohort.member_count} member(s)</p>
        <Link href="/" className="text-xs text-brand-primary underline">
          ← Back
        </Link>
      </div>
      <div className="grid gap-6 md:grid-cols-[2fr,1fr]">
        <div className="rounded-xl border border-white/10 bg-white/5">
          <div className="flex items-center justify-between border-b border-white/10 px-6 py-4 text-xs uppercase tracking-[0.2em] text-slate-400">
            <span>Rankings</span>
            <RankingStrategySelect cohortId={cohort.id} currentStrategy={strategy} />
          </div>
          {rankings.length === 0 ? (
            <p className="p-6 text-sm text-slate-400">No rankings yet.</p>
          ) : (
            <ol>
              {rankings.map((item) => (
                <li key={item.film_id} className="border-b border-white/5 px-6 py-4 last:border-b-0">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <p className="text-lg font-medium text-white">
                        #{item.rank ?? "?"} {item.title}
                      </p>
                      <p className="text-xs text-slate-500">{item.slug}</p>
                    </div>
                    <div className="text-right text-xs uppercase text-slate-500">
                      <p>Score {item.score.toFixed(3)}</p>
                      <p>Distribution {item.distribution_label ?? "mixed"}</p>
                    </div>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-sm text-slate-300">
                    <p>{item.watchers?.toLocaleString() ?? "—"} watchers</p>
                    <p>Avg {formatAverage(item.avg_rating)}</p>
                    <p>{formatPercent(item.favorite_rate)} favorites</p>
                    <p>{formatPercent(item.like_rate)} likes</p>
                    <p>Consensus {item.consensus_strength?.toFixed(2) ?? "—"}</p>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </div>
        <div>
          <CohortActions cohortId={cohort.id} currentLabel={cohort.label} />
        </div>
      </div>
    </section>
  );
}
