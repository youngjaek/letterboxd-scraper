const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const cards = [
  {
    title: "Cohort dashboard",
    body: "Track membership, last sync, and failure modes per cohort.",
  },
  {
    title: "Ranking explorer",
    body: "Apply release year, watcher, and divergence filters powered by cached stats.",
  },
  {
    title: "Saved filters",
    body: "Persist smart lists and export CSVs for sharing.",
  },
  {
    title: "Job timeline",
    body: "Inspect the scrape → enrich → stats pipeline without using the CLI.",
  },
];

export default function Home() {
  return (
    <section className="mx-auto flex max-w-5xl flex-col gap-10">
      <header className="space-y-4">
        <p className="text-sm uppercase tracking-[0.3em] text-brand-accent">Phase 3</p>
        <h1 className="text-4xl font-semibold">Letterboxd Cohort Control Room</h1>
        <p className="text-base text-slate-300">
          This private alpha frontend will call the FastAPI backend running at
          <span className="font-mono text-white"> {apiBase}</span>. Hook the UI up to the API once
          auth, cohort CRUD, and stats endpoints are available.
        </p>
      </header>
      <div className="grid gap-4 md:grid-cols-2">
        {cards.map((card) => (
          <article key={card.title} className="rounded-xl border border-white/10 bg-white/5 p-6 shadow-lg">
            <h2 className="text-xl font-semibold text-brand-primary">{card.title}</h2>
            <p className="mt-2 text-sm text-slate-200">{card.body}</p>
          </article>
        ))}
      </div>
      <footer className="text-sm text-slate-400">
        Need to run the backend? Start it via
        <code className="mx-2 rounded bg-black/40 px-2 py-1 text-xs">uvicorn apps.api.main:app --reload</code>
        then point this app to it.
      </footer>
    </section>
  );
}
