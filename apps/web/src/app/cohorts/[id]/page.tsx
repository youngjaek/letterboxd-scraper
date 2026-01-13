import Link from "next/link";

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function fetchCohort(id: string) {
  const res = await fetch(`${apiBase}/cohorts/${id}`, { cache: "no-store" });
  if (!res.ok) {
    return null;
  }
  return res.json();
}

async function fetchRankings(id: string) {
  const res = await fetch(`${apiBase}/cohorts/${id}/rankings?limit=50`, { cache: "no-store" });
  if (!res.ok) {
    return [];
  }
  return res.json();
}

export default async function CohortRankingsPage({ params }: { params: { id: string } }) {
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
  const rankings = await fetchRankings(params.id);
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
      <div className="rounded-xl border border-white/10 bg-white/5">
        {rankings.length === 0 ? (
          <p className="p-6 text-sm text-slate-400">No rankings yet.</p>
        ) : (
          <ol>
            {rankings.map((item: any) => (
              <li key={item.film_id} className="border-b border-white/5 px-6 py-4 last:border-b-0">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-lg font-medium text-white">
                      #{item.rank ?? "?"} {item.title}
                    </p>
                    <p className="text-xs text-slate-400">{item.slug}</p>
                  </div>
                  <div className="text-right text-sm text-slate-400">
                    <p>{item.avg_rating?.toFixed(2) ?? "--"} avg</p>
                    <p className="text-xs">{item.watchers ?? 0} watchers</p>
                  </div>
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}
