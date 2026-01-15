"use client";

import { useMemo, useState } from "react";

type HistogramBin = {
  key: string;
  label: string;
  count: number;
};

export function RatingHistogram({
  bins,
  watchers,
}: {
  bins: HistogramBin[];
  watchers: number | null;
}) {
  const total = watchers ?? 0;
  const orderedBins = useMemo(() => bins ?? [], [bins]);
  const maxCount = useMemo(
    () => Math.max(...orderedBins.map((bin) => bin.count), 1),
    [orderedBins],
  );
  const [hovered, setHovered] = useState<HistogramBin | null>(null);

  function handleEnter(bin: HistogramBin) {
    setHovered(bin);
  }

  function handleLeave() {
    setHovered(null);
  }

  return (
    <div className="space-y-1">
      <div className="flex items-end h-[72px] overflow-hidden rounded bg-black/20">
        {orderedBins.map((bin) => {
          const pctOfMax = bin.count > 0 ? bin.count / maxCount : 0;
          const height = bin.count > 0 ? Math.max(2, pctOfMax * 64) : 1;
          const pct = total > 0 ? (bin.count / total) * 100 : 0;
          return (
            <div
              key={bin.key}
              className="relative flex-1 h-full"
              onMouseEnter={() => handleEnter(bin)}
              onMouseLeave={handleLeave}
            >
              <div
                className="absolute bottom-0 left-[1px] right-[1px] rounded-sm bg-gradient-to-t from-brand-primary/40 via-brand-primary/70 to-brand-primary/95 transition-all duration-200"
                style={{
                  height: `${height}px`,
                  opacity: hovered && hovered.key !== bin.key ? 0.35 : 1,
                }}
                title={`${bin.label}: ${bin.count.toLocaleString()} ratings${
                  total > 0 ? ` (${pct.toFixed(1)}%)` : ""
                }`}
              />
            </div>
          );
        })}
      </div>
      <div className="text-[0.6rem] uppercase tracking-[0.2em] text-slate-400">
        {hovered ? (
          <>
            <span className="font-semibold text-white">{hovered.label}</span>{" "}
            · {hovered.count.toLocaleString()} rating{hovered.count === 1 ? "" : "s"}
            {total > 0 && <> ({((hovered.count / total) * 100).toFixed(1)}%)</>}
          </>
        ) : (
          "Rating distribution"
        )}
      </div>
    </div>
  );
}
