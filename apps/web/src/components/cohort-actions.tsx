"use client";

import { useState, FormEvent } from "react";

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const apiKey = process.env.NEXT_PUBLIC_API_KEY;

export function CohortActions({ cohortId, currentLabel }: { cohortId: number; currentLabel: string }) {
  const [label, setLabel] = useState(currentLabel);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function request(path: string, options: RequestInit) {
    const headers = {
      "Content-Type": "application/json",
      ...(apiKey ? { "X-API-Key": apiKey } : {}),
      ...(options.headers || {}),
    };
    const response = await fetch(`${apiBase}${path}`, { ...options, headers });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `Failed with status ${response.status}`);
    }
    return response;
  }

  async function handleRename(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setMessage(null);
    setError(null);
    try {
      await request(`/cohorts/${cohortId}?label=${encodeURIComponent(label)}`, {
        method: "PATCH",
      });
      setMessage("Renamed cohort.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rename failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleSync() {
    setLoading(true);
    setMessage(null);
    setError(null);
    try {
      await request(`/cohorts/${cohortId}/sync`, { method: "POST", body: JSON.stringify({}) });
      setMessage("Sync triggered.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sync failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete() {
    if (!confirm("Delete this cohort?")) {
      return;
    }
    setLoading(true);
    setMessage(null);
    setError(null);
    try {
      await request(`/cohorts/${cohortId}`, { method: "DELETE" });
      setMessage("Deleted cohort.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4 rounded-xl border border-white/10 bg-white/5 p-5">
      <h3 className="text-lg font-semibold text-brand-primary">Manage Cohort</h3>
      <form onSubmit={handleRename} className="space-y-2">
        <label className="block text-xs uppercase text-slate-400">Label</label>
        <div className="flex gap-2">
          <input
            className="flex-1 rounded border border-white/10 bg-black/30 px-3 py-2 text-sm"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
          />
          <button className="rounded bg-brand-primary px-4 py-2 text-sm font-semibold text-black" disabled={loading}>
            Rename
          </button>
        </div>
      </form>
      <div className="flex gap-2">
        <button
          className="flex-1 rounded border border-white/20 px-3 py-2 text-sm text-white"
          onClick={handleSync}
          disabled={loading}
        >
          Sync now
        </button>
        <button
          className="flex-1 rounded border border-red-500 px-3 py-2 text-sm text-red-400"
          onClick={handleDelete}
          disabled={loading}
        >
          Delete
        </button>
      </div>
      {message && <p className="text-sm text-green-400">{message}</p>}
      {error && <p className="text-sm text-red-400">{error}</p>}
    </div>
  );
}
