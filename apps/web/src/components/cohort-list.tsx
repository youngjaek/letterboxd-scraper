import Image from "next/image";
import Link from "next/link";
import type { CohortCardData } from "@/lib/cohort-data";

type CohortListProps = {
  cohorts: CohortCardData[];
};

export function CohortList({ cohorts }: CohortListProps) {
  if (cohorts.length === 0) {
    return (
      <div className="panel text-sm text-[color:var(--text-soft)]">
        No canons found.
      </div>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {cohorts.map(({ cohort, preview, descriptor, freshnessLabel }) => (
        <article key={cohort.id} className="panel interactive-card flex h-full flex-col gap-4">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="truncate text-lg font-semibold text-[color:var(--text)]">
                {cohort.seed_username ? `@${cohort.seed_username}` : cohort.label}
              </p>
              <p className="truncate text-sm text-[color:var(--text-soft)]">{descriptor}</p>
            </div>
            <span className="status-chip">{cohort.member_count}</span>
          </div>

          <div className="flex gap-2">
            {preview.slice(0, 3).map((film) => (
              <div
                key={film.film_id}
                className="poster-tile min-h-[7rem] flex-1"
              >
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

          <div className="space-y-1">
            {preview.slice(0, 2).map((film, index) => (
              <div key={film.film_id} className="flex items-center justify-between gap-3 text-sm">
                <p className="min-w-0 truncate text-[color:var(--text)]">
                  {index + 1}. {film.title}
                </p>
                <p className="whitespace-nowrap text-[color:var(--text-muted)]">
                  {film.watchers?.toLocaleString() ?? "N/A"}
                </p>
              </div>
            ))}
          </div>

          <div className="mt-auto flex items-center justify-between gap-3 border-t border-white/5 pt-4">
            <p className="text-xs text-[color:var(--text-muted)]">Updated {freshnessLabel}</p>
            <Link href={`/cohorts/${cohort.id}`} className="button-secondary px-4 py-2 text-xs">
              Open
            </Link>
          </div>
        </article>
      ))}
    </div>
  );
}
