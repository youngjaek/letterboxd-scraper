"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
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
    statusLabel = "Syncing...";
  }

  const statusClass =
    currentTaskStage === "error" ? "text-red-300" : isSyncing ? "text-amber-200" : "text-[color:var(--text-strong)]";

  if (demoLocked) {
    return (
      <div className="panel-soft space-y-4 text-sm text-[color:var(--text-muted)]">
        <div className="space-y-2">
          <p className="eyebrow">Operations</p>
          <h3 className="text-xl font-semibold text-[color:var(--text-strong)]">This cohort is viewable but locked.</h3>
        </div>
        <p className="leading-7">
          Preview visitors can explore the ranking board and filters, but sync, rename, and delete actions stay
          disabled.
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
      setStatus("Cohort renamed.");
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
    if (!confirm("Delete this cohort? This cannot be undone.")) {
      return;
    }
    setBusy(true);
    setStatus(null);
    setError(null);
    try {
      await sendRequest(`/cohorts/${cohortId}`, { method: "DELETE" });
      setStatus("Cohort deleted. Return to the app index to continue browsing.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel-soft space-y-5">
      <div className="space-y-2">
        <p className="eyebrow">Operations</p>
        <h3 className="text-xl font-semibold text-[color:var(--text-strong)]">Control the cohort lifecycle.</h3>
        <p className="text-xs uppercase tracking-[0.24em] text-[color:var(--text-faint)]">
          Status: <span className={statusClass}>{statusLabel}</span>
        </p>
      </div>

      <form onSubmit={handleRename} className="space-y-3">
        <label htmlFor="rename-label" className="field-label">
          Cohort label
        </label>
        <div className="flex flex-col gap-3 sm:flex-row">
          <input
            id="rename-label"
            className="field-input flex-1"
            value={label}
            onChange={(event) => setLabel(event.target.value)}
          />
          <button
            type="submit"
            className="button-secondary whitespace-nowrap disabled:cursor-not-allowed disabled:opacity-60"
            disabled={busy}
          >
            Rename
          </button>
        </div>
      </form>

      <div className="grid gap-3 sm:grid-cols-2">
        {isSyncing ? (
          <button
            type="button"
            className="button-secondary border-amber-200/40 text-amber-100 disabled:cursor-not-allowed disabled:opacity-60"
            onClick={handleStop}
            disabled={busy}
          >
            Stop sync
          </button>
        ) : (
          <button
            type="button"
            className="button-primary disabled:cursor-not-allowed disabled:opacity-60"
            onClick={handleSync}
            disabled={busy}
          >
            Sync now
          </button>
        )}
        <button
          type="button"
          className="button-ghost border-red-300/30 text-red-200 disabled:cursor-not-allowed disabled:opacity-60"
          onClick={handleDelete}
          disabled={busy}
        >
          Delete cohort
        </button>
      </div>

      {status ? <p className="text-sm text-emerald-300">{status}</p> : null}
      {error ? <p className="text-sm text-red-300">{error}</p> : null}
    </div>
  );
}
