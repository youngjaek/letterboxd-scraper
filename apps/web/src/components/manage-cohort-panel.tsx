"use client";

import { useState } from "react";
import { CohortActions } from "./cohort-actions";
import { CohortMembersPanel } from "./cohort-members-panel";
import { ScrapeProgressPanel, type ScrapeProgress } from "./scrape-progress-panel";

type ManagePanelProps = {
  cohortId: number;
  label: string;
  currentTaskId?: string | null;
  members: Array<{ username: string; avatar_url: string | null }>;
  scrapeStatus: ScrapeProgress | null;
};

export function ManageCohortPanel({
  cohortId,
  label,
  currentTaskId,
  members,
  scrapeStatus,
}: ManagePanelProps) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-white/10 bg-white/5">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="flex w-full items-center justify-between border-b border-white/10 px-6 py-4 text-xs uppercase tracking-[0.2em] text-slate-400"
      >
        <span>Manage Cohort</span>
        <span className="text-slate-300">{open ? "Hide" : "Show"}</span>
      </button>
      {open && (
        <div className="space-y-6 px-6 py-6">
          <div className="grid gap-6 lg:grid-cols-2">
            <CohortActions cohortId={cohortId} currentLabel={label} currentTaskId={currentTaskId} />
            <CohortMembersPanel members={members} />
          </div>
          <ScrapeProgressPanel cohortId={cohortId} initialStatus={scrapeStatus} />
        </div>
      )}
    </div>
  );
}
