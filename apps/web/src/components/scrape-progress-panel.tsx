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
      return "Preview snapshot - no live scrapes";
    }
    if (currentStage === "refreshing") {
      return "Gathering follow graph...";
    }
    if (currentStage === "scraping") {
      return total > 0 ? `Scraping ${completed}/${total}` : "Scraping members...";
    }
    if (currentStage === "computing") {
      return "Computing stats and rankings...";
    }
    if (currentStage === "error") {
      return "Sync failed. Retry when ready.";
    }
    if (displayStatus === "running") {
      return total > 0 ? `Scraping ${completed}/${total}` : "Scraping members...";
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
    <div className="panel-soft space-y-4">
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <p className="eyebrow">Pipeline activity</p>
          {activeStageLabel ? <span className="status-chip">{activeStageLabel}</span> : null}
        </div>
        <p className="text-sm text-[color:var(--text-muted)]">{subtitle}</p>
      </div>

      <div className="h-2 w-full overflow-hidden rounded-full bg-white/10">
        <div
          className="h-full bg-gradient-to-r from-[color:var(--gold)] to-[color:var(--red)] transition-all"
          style={{ width: `${progressPercent}%` }}
        />
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <div className="metric-card">
          <p className="metric-label">Completed</p>
          <p className="mt-2 text-lg font-semibold text-[color:var(--text-strong)]">{completed}</p>
        </div>
        <div className="metric-card">
          <p className="metric-label">Queued</p>
          <p className="mt-2 text-lg font-semibold text-[color:var(--text-strong)]">{queued}</p>
        </div>
        <div className="metric-card">
          <p className="metric-label">Failed</p>
          <p className="mt-2 text-lg font-semibold text-[color:var(--text-strong)]">{failed}</p>
        </div>
      </div>

      {currentStage === "scraping" && activeList.length > 0 ? (
        <div className="space-y-3">
          <p className="field-label">Currently scraping</p>
          <ul className="grid gap-2 sm:grid-cols-2">
            {activeList.map((member) => (
              <li key={member.username} className="rounded-2xl border border-white/5 bg-black/20 px-3 py-2 text-sm">
                <span className="font-semibold text-[color:var(--text-strong)]">@{member.username}</span>{" "}
                <span className="text-[color:var(--text-faint)]">{member.mode}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {recent.length > 0 ? (
        <div className="space-y-3">
          <p className="field-label">Recently finished</p>
          <ul className="grid gap-2 sm:grid-cols-2">
            {recent.map((member) => (
              <li key={member.username} className="rounded-2xl border border-white/5 bg-black/20 px-3 py-2 text-sm">
                <span className="font-semibold text-[color:var(--text-strong)]">@{member.username}</span>{" "}
                <span className={member.status === "failed" ? "text-red-300" : "text-emerald-300"}>{member.status}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
