"use client";

import { useCallback, useEffect, useState } from "react";
import { getApiBase } from "@/lib/api-base";
import { isDemoMode } from "@/lib/demo-flags";

const apiBase = getApiBase();
const apiKey = process.env.NEXT_PUBLIC_API_KEY;

export type ScrapeMemberStatus = {
  username: string;
  status: string;
  mode: string;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
};

export type ScrapeProgress = {
  status: string;
  run_id: number | null;
  run_type: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  total_members: number;
  completed: number;
  failed: number;
  queued: number;
  in_progress: ScrapeMemberStatus[];
  recent_finished: ScrapeMemberStatus[];
  current_stage?: string | null;
};

async function fetchStatus(cohortId: number): Promise<ScrapeProgress | null> {
  try {
    const res = await fetch(`${apiBase}/cohorts/${cohortId}/scrape-status`, {
      headers: {
        ...(apiKey ? { "X-API-Key": apiKey } : {}),
      },
      cache: "no-store",
    });
    if (!res.ok) {
      return null;
    }
    return res.json();
  } catch {
    return null;
  }
}

export function ScrapeProgressPanel({
  cohortId,
  initialStatus,
  onStatusUpdate,
}: {
  cohortId: number;
  initialStatus: ScrapeProgress | null;
  onStatusUpdate?: (status: ScrapeProgress | null) => void;
}) {
  const [status, setStatus] = useState<ScrapeProgress | null>(initialStatus);
  const demoLocked = isDemoMode;

  useEffect(() => {
    setStatus(initialStatus);
  }, [initialStatus]);

  const emitUpdate = useCallback(
    (next: ScrapeProgress | null) => {
      if (onStatusUpdate) {
        onStatusUpdate(next);
      }
    },
    [onStatusUpdate],
  );

  useEffect(() => {
    if (demoLocked) {
      return;
    }
    let cancelled = false;
    const poll = async () => {
      const next = await fetchStatus(cohortId);
      if (!cancelled) {
        setStatus(next);
        emitUpdate(next);
      }
    };
    poll();
    const interval = setInterval(poll, 5000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [cohortId, demoLocked, emitUpdate]);

  const displayStatus = status?.status ?? "idle";
  const total = status?.total_members ?? 0;
  const completed = status?.completed ?? 0;
  const percent = total > 0 ? Math.round((completed / total) * 100) : 0;
  const activeList = (status?.in_progress ?? []).slice(0, 5);
  const recent = (status?.recent_finished ?? []).slice(0, 5);
  const queued = status?.queued ?? 0;
  const failed = status?.failed ?? 0;
  const currentStage = status?.current_stage ?? null;
  const stageLabels: Record<string, string> = {
    refreshing: "Gathering follow graph",
    scraping: "Scraping ratings",
    computing: "Computing rankings",
    error: "Sync failed",
  };
  const activeStageLabel = currentStage ? stageLabels[currentStage] ?? currentStage : null;
  const subtitle = (() => {
    if (demoLocked) {
      return "Demo snapshot · no live scrapes";
    }
    if (currentStage === "refreshing") {
      return "Gathering follow graph…";
    }
    if (currentStage === "scraping") {
      return total > 0 ? `Scraping ${completed}/${total}` : "Scraping members…";
    }
    if (currentStage === "computing") {
      return "Computing stats & rankings…";
    }
    if (currentStage === "error") {
      return "Sync failed. Retry when ready.";
    }
    if (displayStatus === "running") {
      return total > 0 ? `Scraping ${completed}/${total}` : "Scraping members…";
    }
    return total > 0 ? `Last run ${displayStatus}` : "No runs yet";
  })();
  const progressPercent =
    currentStage === "scraping"
      ? percent
      : currentStage === "computing"
        ? 100
        : currentStage === "refreshing"
          ? 15
          : percent;

  return (
    <div className="rounded-xl border border-white/10 bg-black/30 p-4">
      <div className="flex flex-col gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-semibold text-white">Pipeline Activity</p>
          {activeStageLabel ? (
            <span className="rounded-full border border-white/15 px-2 py-0.5 text-[0.6rem] uppercase tracking-[0.3em] text-slate-200">
              {activeStageLabel}
            </span>
          ) : null}
        </div>
        <p className="text-xs text-slate-400">{subtitle}</p>
      </div>
      <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-white/10">
        <div className="h-full bg-brand-primary transition-all" style={{ width: `${progressPercent}%` }} />
      </div>
      <div className="mt-3 flex flex-wrap gap-4 text-xs text-slate-300">
        <span>Completed: {completed}</span>
        <span>Queued: {queued}</span>
        <span>Failed: {failed}</span>
      </div>
      {currentStage === "scraping" && activeList.length > 0 && (
        <div className="mt-4">
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Currently Scraping</p>
          <ul className="mt-2 grid gap-2 sm:grid-cols-2">
            {activeList.map((member) => (
              <li key={member.username} className="rounded border border-white/10 bg-white/5 px-3 py-2 text-sm text-white">
                @{member.username} <span className="text-xs text-slate-400">{member.mode}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {recent.length > 0 && (
        <div className="mt-4">
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Recently Finished</p>
          <ul className="mt-2 grid gap-2 sm:grid-cols-2">
            {recent.map((member) => (
              <li key={member.username} className="rounded border border-white/5 bg-black/20 px-3 py-2 text-sm text-slate-200">
                @{member.username}{" "}
                <span className={member.status === "failed" ? "text-red-400" : "text-green-400"}>
                  {member.status}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
