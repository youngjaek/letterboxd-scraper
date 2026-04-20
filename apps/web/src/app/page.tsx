import Image from "next/image";
import Link from "next/link";
import { DemoBanner } from "@/components/demo-banner";
import { buildCohortCards, fetchVisibleCohorts } from "@/lib/cohort-data";

export default async function Home() {
  const cohorts = await fetchVisibleCohorts();
  const cards = await buildCohortCards(cohorts, 6, 4);
  const posters = cards.flatMap((card) => card.preview).slice(0, 6);

  return (
    <section className="mx-auto flex w-full max-w-5xl flex-col gap-8 pb-12">
      <DemoBanner />

      <section className="flex flex-col items-center gap-6 pt-8 text-center">
        <p className="eyebrow">For Letterboxd users</p>
        <h1 className="display-title max-w-3xl">See a user&apos;s friends&apos; canon of films.</h1>
        <p className="max-w-2xl text-base leading-7 text-[color:var(--text-soft)]">
          Search a username, open the canon, and browse the films their circle loves most.
        </p>
        <div className="flex flex-wrap justify-center gap-3">
          <Link href="/cohorts" className="button-primary">
            Browse canons
          </Link>
          <Link href="/cohorts#build" className="button-secondary">
            Build a canon
          </Link>
        </div>
      </section>

      <section className="panel flex flex-col gap-5">
        <div className="grid gap-3 grid-cols-3 sm:grid-cols-6">
          {posters.map((film) => (
            <div key={film.film_id} className="poster-tile">
              {film.poster_url ? (
                <Image src={film.poster_url} alt={`${film.title} poster`} fill className="object-cover" unoptimized />
              ) : (
                <div className="flex h-full items-center justify-center text-[0.65rem] text-[color:var(--text-muted)]">
                  No poster
                </div>
              )}
            </div>
          ))}
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          <div className="panel-soft interactive-panel text-center">
            <p className="eyebrow">Search</p>
            <p className="mt-2 text-lg font-semibold text-[color:var(--text)]">Find a user</p>
          </div>
          <div className="panel-soft interactive-panel text-center">
            <p className="eyebrow">Browse</p>
            <p className="mt-2 text-lg font-semibold text-[color:var(--text)]">Open the canon</p>
          </div>
          <div className="panel-soft interactive-panel text-center">
            <p className="eyebrow">Build</p>
            <p className="mt-2 text-lg font-semibold text-[color:var(--text)]">Request a new one</p>
          </div>
        </div>
      </section>
    </section>
  );
}
