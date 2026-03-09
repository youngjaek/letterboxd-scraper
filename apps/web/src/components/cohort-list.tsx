"use client";

import Link from "next/link";
import { useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import type { CohortSummary } from "@/types/cohort";

type CohortListProps = {
  cohorts: CohortSummary[];
};

export function CohortList({ cohorts }: CohortListProps) {
  const router = useRouter();
  const prefetched = useRef<Set<number>>(new Set());

  const handlePrefetch = useCallback(
    (cohortId: number) => {
      if (prefetched.current.has(cohortId)) {
        return;
      }
      prefetched.current.add(cohortId);
      router.prefetch(`/cohorts/${cohortId}`);
    },
    [router],
  );

  if (cohorts.length === 0) {
    return <p className="p-6 text-sm text-slate-400">No cohorts are available in this demo right now.</p>;
  }

  return (
    <ul>
      {cohorts.map((cohort) => (
        <li key={cohort.id} className="border-b border-white/5 px-6 py-4 last:border-b-0">
          <Link
            href={`/cohorts/${cohort.id}`}
            className="flex items-center justify-between"
            onPointerEnter={() => handlePrefetch(cohort.id)}
            onFocus={() => handlePrefetch(cohort.id)}
            onTouchStart={() => handlePrefetch(cohort.id)}
          >
            <div>
              <p className="text-lg font-medium text-brand-primary">{cohort.label}</p>
              <p className="text-xs text-slate-400">
                ID {cohort.id} · Created {new Date(cohort.created_at).toLocaleDateString()}
              </p>
            </div>
            <div className="text-right text-sm text-slate-200">
              <p>{cohort.member_count} member(s)</p>
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}
