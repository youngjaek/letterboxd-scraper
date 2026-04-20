import { CohortList } from "@/components/cohort-list";
import { CreateCohortForm } from "@/components/create-cohort-form";
import { DemoBanner } from "@/components/demo-banner";
import { buildCohortCards, fetchVisibleCohorts, filterCohortCards } from "@/lib/cohort-data";

export default async function CohortsIndexPage({
  searchParams,
}: {
  searchParams?: Record<string, string | string[] | undefined>;
}) {
  const queryValue = Array.isArray(searchParams?.query) ? searchParams?.query[0] : searchParams?.query;
  const query = queryValue?.trim() ?? "";
  const cohorts = await fetchVisibleCohorts();
  const cards = await buildCohortCards(cohorts, 24, 3);
  const filteredCards = filterCohortCards(cards, query);

  return (
    <section className="mx-auto flex w-full max-w-6xl flex-col gap-8 pb-12">
      <DemoBanner />

      <header className="space-y-4">
        <div className="space-y-2">
          <p className="eyebrow">Search</p>
          <h1 className="section-title">Search a user&apos;s friends&apos; canon</h1>
        </div>

        <form action="/cohorts" method="get" className="panel flex flex-col gap-3 sm:flex-row">
          <input
            type="search"
            name="query"
            defaultValue={query}
            placeholder="Search a username or canon"
            className="field-input flex-1"
          />
          <button type="submit" className="button-primary sm:min-w-[9rem]">
            Search
          </button>
        </form>
      </header>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.8fr)_minmax(22rem,1fr)]">
        <section className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm text-[color:var(--text-soft)]">
                {query ? `Results for "${query}"` : "Browse all available canons"}
              </p>
            </div>
            <span className="status-chip">{filteredCards.length} results</span>
          </div>
          <CohortList cohorts={filteredCards} />
        </section>

        <aside id="build" className="space-y-4">
          <CreateCohortForm />
        </aside>
      </div>
    </section>
  );
}
