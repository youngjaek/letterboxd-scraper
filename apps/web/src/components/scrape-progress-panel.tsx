"use client";

import { useEffect, useMemo, useState } from "react";

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const apiKey = process.env.NEXT_PUBLIC_API_KEY;

type ScrapeMemberStatus = {
  username: string;
  status: string;
  mode: string;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
};

type ScrapeProgress = {
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
}: {
  cohortId: number;
  initialStatus: ScrapeProgress | null;
}) {
  const [status, setStatus] = useState<ScrapeProgress | null>(initialStatus);

  useEffect(() => {
    const interval = setInterval(async () => {
      const next = await fetchStatus(cohortId);
      if (next) {
        setStatus(next);
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [cohortId]);

  const displayStatus = status?.status ?? "idle";
  const total = status?.total_members ?? 0;
  const completed = status?.completed ?? 0;
  const percent = total > 0 ? Math.round((completed / total) * 100) : 0;
  const activeList = (status?.in_progress ?? []).slice(0, 5);
  const recent = (status?.recent_finished ?? []).slice(0, 5);
  const subtitle =
    displayStatus === "running"
      ? `Scraping ${completed}/${total}`
      : total > 0
        ? `Last run ${displayStatus}`
        : "No runs yet";

  return (
    <div className="rounded-xl border border-white/10 bg-black/30 p-4">
      <div className="flex flex-col gap-1">
        <p className="text-sm font-semibold text-white">Pipeline Activity</p>
        <p className="text-xs text-slate-400">{subtitle}</p>
      </div>
      <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-white/10">
        <div className="h-full bg-brand-primary transition-all" style={{ width: `${percent}%` }} />
      </div>
      <div className="mt-3 flex flex-wrap gap-4 text-xs text-slate-300">
        <span>Completed: {completed}</span>
        <span>Queued: {status.queued}</span>
        <span>Failed: {status.failed}</span>
      </div>
      {activeList.length > 0 && (
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
