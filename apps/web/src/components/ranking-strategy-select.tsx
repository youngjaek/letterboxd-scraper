"use client";

import { type ChangeEvent, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

const STRATEGIES: Array<{ value: string; label: string }> = [
  { value: "cohort_affinity", label: "Cohort Affinity" },
  { value: "bayesian", label: "Bayesian Mean" },
];

export function RankingStrategySelect({ cohortId, currentStrategy }: { cohortId: number; currentStrategy: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const options = useMemo(() => STRATEGIES, []);

  function handleChange(event: ChangeEvent<HTMLSelectElement>) {
    const nextStrategy = event.target.value;
    const params = new URLSearchParams(searchParams?.toString() ?? "");
    if (nextStrategy === "cohort_affinity") {
      params.delete("strategy");
    } else {
      params.set("strategy", nextStrategy);
    }
    const query = params.toString();
    const base = pathname || `/cohorts/${cohortId}`;
    router.push(query ? `${base}?${query}` : base);
  }

  return (
    <label className="text-[0.6rem] font-semibold tracking-[0.2em] text-slate-500">
      Strategy
      <select
        className="ml-3 rounded border border-white/20 bg-black/40 px-2 py-1 text-[0.65rem] font-semibold uppercase tracking-[0.2em] text-white"
        value={currentStrategy}
        onChange={handleChange}
      >
        {options.map((option) => (
          <option value={option.value} key={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}
