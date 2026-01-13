import { CreateCohortForm } from "@/components/create-cohort-form";

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type CohortSummary = {
  id: number;
  label: string;
  member_count: number;
  created_at: string;
};

async function fetchCohorts(): Promise<CohortSummary[]> {
  const res = await fetch(`${apiBase}/cohorts`, { cache: "no-store" });
  if (!res.ok) {
    console.warn("Failed to load cohorts", res.status, await res.text());
    return [];
  }
  return res.json();
}

export default async function Home() {
  const cohorts = await fetchCohorts();
  return (
    <section className="mx-auto flex max-w-5xl flex-col gap-10">
      <header className="space-y-4">
        <p className="text-sm uppercase tracking-[0.3em] text-brand-accent">Phase 3</p>
        <h1 className="text-4xl font-semibold">Letterboxd Cohort Control Room</h1>
        <p className="text-base text-slate-300">
          FastAPI base:
          <span className="font-mono text-white"> {apiBase}</span>
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
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-lg font-medium text-brand-primary">{cohort.label}</p>
                        <p className="text-xs text-slate-400">ID {cohort.id} · Created {new Date(cohort.created_at).toLocaleDateString()}</p>
                      </div>
                      <div className="text-right text-sm text-slate-200">
                        <p>{cohort.member_count} member(s)</p>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
        <div>
          <CreateCohortForm />
        </div>
      </div>
      <footer className="text-sm text-slate-400">
        Backend running? Start via
        <code className="mx-2 rounded bg-black/40 px-2 py-1 text-xs">uvicorn apps.api.main:app --reload</code>
        and ensure `NEXT_PUBLIC_API_BASE_URL` targets it.
      </footer>
    </section>
  );
}
