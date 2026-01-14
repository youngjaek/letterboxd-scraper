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
  poster_url: string | null;
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
                <li key={item.film_id} className="border-b border-white/5 px-6 py-5 last:border-b-0">
                  <div className="flex flex-col gap-4 sm:flex-row sm:gap-6">
                    <div className="w-full max-w-[120px] flex-shrink-0">
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
                    <div className="flex flex-1 flex-col gap-3">
                      <div className="flex flex-col gap-1 md:flex-row md:items-baseline md:justify-between">
                        <div>
                          <p className="text-sm uppercase tracking-[0.3em] text-brand-accent">
                            #{item.rank ?? "?"}
                          </p>
                          <Link
                            href={letterboxdUrl(item.slug)}
                            target="_blank"
                            className="text-xl font-semibold text-white hover:text-brand-primary"
                          >
                            {item.title}
                          </Link>
                          <p className="text-xs text-slate-500">{item.slug}</p>
                        </div>
                        <div className="text-right text-xs uppercase text-slate-400">
                          <p className="font-semibold text-white">
                            Score <span className="text-brand-primary">{item.score.toFixed(3)}</span>
                          </p>
                          <p>Distribution {item.distribution_label ?? "mixed"}</p>
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-3">
                        <StatPill label="Watchers" value={item.watchers?.toLocaleString() ?? "—"} />
                        <StatPill label="Avg" value={formatAverage(item.avg_rating)} />
                        <StatPill label="Fav %" value={formatPercent(item.favorite_rate)} />
                        <StatPill label="Like %" value={formatPercent(item.like_rate)} />
                        <StatPill
                          label="Consensus"
                          value={item.consensus_strength !== null && item.consensus_strength !== undefined ? item.consensus_strength.toFixed(2) : "—"}
                        />
                      </div>
                    </div>
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
