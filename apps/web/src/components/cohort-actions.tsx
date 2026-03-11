"use client";

import { useRouter } from "next/navigation";
import { useState, FormEvent } from "react";
import { getApiBase } from "@/lib/api-base";
import { isDemoMode } from "@/lib/demo-flags";

const apiBase = getApiBase();
const apiKey = process.env.NEXT_PUBLIC_API_KEY;

async function sendRequest(path: string, init: RequestInit = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(apiKey ? { "X-API-Key": apiKey } : {}),
    ...(init.headers || {}),
  };
  const response = await fetch(`${apiBase}${path}`, { ...init, headers });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Failed with status ${response.status}`);
  }
  return response;
}

type CohortActionsProps = {
  cohortId: number;
  currentLabel: string;
  currentTaskId?: string | null;
  currentTaskStage?: string | null;
};

export function CohortActions({ cohortId, currentLabel, currentTaskId, currentTaskStage }: CohortActionsProps) {
  const demoLocked = isDemoMode;
  const [label, setLabel] = useState(currentLabel);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const router = useRouter();
  const syncingStages = new Set(["refreshing", "scraping", "computing"]);
  const stageIsActive = currentTaskStage ? syncingStages.has(currentTaskStage) : false;
  const hasStageSignal = currentTaskStage !== undefined;
  const isSyncing = stageIsActive || (!hasStageSignal && Boolean(currentTaskId));
  const stageLabels: Record<string, string> = {
    refreshing: "Gathering follow graph",
    scraping: "Scraping ratings",
    computing: "Computing rankings",
    error: "Sync failed",
  };
  let statusLabel = "Idle";
  if (currentTaskStage && stageLabels[currentTaskStage]) {
    statusLabel = stageLabels[currentTaskStage];
  } else if (isSyncing) {
    statusLabel = "Syncing…";
  }
  const statusClass =
    currentTaskStage === "error" ? "text-red-400" : isSyncing ? "text-yellow-300" : "text-slate-100";

  if (demoLocked) {
    return (
      <div className="space-y-4 rounded-xl border border-white/10 bg-white/5 p-5 text-sm text-slate-300">
        <h3 className="text-lg font-semibold text-brand-primary">Manage Cohort</h3>
        <p>
          Demo visitors can explore rankings, but sync controls stay disabled in this read-only preview.
        </p>
      </div>
    );
  }

  async function handleRename(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setStatus(null);
    setError(null);
    try {
      await sendRequest(`/cohorts/${cohortId}?label=${encodeURIComponent(label)}`, { method: "PATCH" });
      setStatus("Renamed cohort.");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rename failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleSync() {
    setBusy(true);
    setStatus(null);
    setError(null);
    try {
      await sendRequest(`/cohorts/${cohortId}/sync`, { method: "POST" });
      setStatus("Sync triggered.");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sync failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleStop() {
    setBusy(true);
    setStatus(null);
    setError(null);
    try {
      await sendRequest(`/cohorts/${cohortId}/sync/stop`, { method: "POST" });
      setStatus("Sync stopped.");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Stop failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!confirm("Delete this cohort?")) return;
    setBusy(true);
    setStatus(null);
    setError(null);
    try {
      await sendRequest(`/cohorts/${cohortId}`, { method: "DELETE" });
      setStatus("Deleted cohort. Reload homepage to see changes.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4 rounded-xl border border-white/10 bg-white/5 p-5">
      <h3 className="text-lg font-semibold text-brand-primary">Manage Cohort</h3>
      <p className="text-xs uppercase tracking-[0.3em] text-slate-400">
        Status:{" "}
        <span className={statusClass}>{statusLabel}</span>
      </p>
      <form onSubmit={handleRename} className="space-y-2">
        <label className="block text-xs uppercase text-slate-400">Label</label>
        <div className="flex gap-2">
          <input
            className="flex-1 rounded border border-white/10 bg-black/30 px-3 py-2 text-sm"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
          />
          <button className="rounded bg-brand-primary px-4 py-2 text-sm font-semibold text-black" disabled={busy}>
            Rename
          </button>
        </div>
      </form>
      <div className="flex gap-2">
        {isSyncing ? (
          <button
            className="flex-1 rounded border border-yellow-400 px-3 py-2 text-sm text-yellow-300"
            onClick={handleStop}
            disabled={busy}
          >
            Stop sync
          </button>
        ) : (
          <button
            className="flex-1 rounded border border-white/20 px-3 py-2 text-sm text-white"
            onClick={handleSync}
            disabled={busy}
          >
            Sync now
          </button>
        )}
        <button
          className="flex-1 rounded border border-red-400 px-3 py-2 text-sm text-red-400"
          onClick={handleDelete}
          disabled={busy}
        >
          Delete
        </button>
      </div>
      {status && <p className="text-sm text-green-400">{status}</p>}
      {error && <p className="text-sm text-red-400">{error}</p>}
    </div>
  );
}
