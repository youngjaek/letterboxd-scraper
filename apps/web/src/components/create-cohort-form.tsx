"use client";

import { useState, FormEvent, useTransition } from "react";
import { useRouter } from "next/navigation";

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const apiKey = process.env.NEXT_PUBLIC_API_KEY;

export function CreateCohortForm({ onCreated }: { onCreated?: () => void }) {
  const [seedUsername, setSeedUsername] = useState("");
  const [label, setLabel] = useState("");
  const [isSubmitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const router = useRouter();
  const [isRefreshing, startTransition] = useTransition();

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      const response = await fetch(`${apiBase}/cohorts/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(apiKey ? { "X-API-Key": apiKey } : {}),
        },
        body: JSON.stringify({ seed_username: seedUsername, label }),
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `Failed with status ${response.status}`);
      }
      setSeedUsername("");
      setLabel("");
      setSuccess("Cohort created!");
      if (onCreated) {
        onCreated();
      }
      startTransition(() => {
        router.refresh();
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="rounded-xl border border-white/10 bg-white/5 p-6 space-y-4">
      <h3 className="text-lg font-semibold text-brand-primary">Create Cohort</h3>
      <p className="text-sm text-slate-400">Uses `NEXT_PUBLIC_API_KEY` for private alpha auth.</p>
      <div className="space-y-1">
        <label className="text-sm text-slate-200">Seed username</label>
        <input
          className="w-full rounded border border-white/10 bg-black/30 px-3 py-2 text-sm"
          value={seedUsername}
          onChange={(event) => setSeedUsername(event.target.value)}
          placeholder="letterboxd_user"
          required
        />
      </div>
      <div className="space-y-1">
        <label className="text-sm text-slate-200">Label</label>
        <input
          className="w-full rounded border border-white/10 bg-black/30 px-3 py-2 text-sm"
          value={label}
          onChange={(event) => setLabel(event.target.value)}
          placeholder="My Critics Cohort"
          required
        />
      </div>
      <button
        type="submit"
        className="rounded bg-brand-primary px-4 py-2 text-sm font-semibold text-black disabled:opacity-60"
        disabled={isSubmitting || isRefreshing}
      >
        {isSubmitting ? "Creating…" : isRefreshing ? "Refreshing…" : "Create cohort"}
      </button>
      {error && <p className="text-sm text-red-400">{error}</p>}
      {success && <p className="text-sm text-green-400">{success}</p>}
    </form>
  );
}
