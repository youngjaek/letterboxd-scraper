"use client";

import { useState, type FormEvent, useTransition } from "react";
import { useRouter } from "next/navigation";
import { getApiBase } from "@/lib/api-base";
import { isDemoMode } from "@/lib/demo-flags";

const apiBase = getApiBase();
const apiKey = process.env.NEXT_PUBLIC_API_KEY;

function DemoLockedNotice() {
  return (
    <div className="panel-soft space-y-4 text-sm text-[color:var(--text-muted)]">
      <div className="space-y-2">
        <p className="eyebrow">Create a cohort</p>
        <h3 className="text-xl font-semibold text-[color:var(--text-strong)]">Creation is disabled in the public preview.</h3>
      </div>
      <p className="leading-7">
        You can still browse the live ranking boards here. To create or sync a cohort, use your local or internal
        Kinoboxd environment.
      </p>
    </div>
  );
}

function CreateCohortFormInner({ onCreated }: { onCreated?: () => void }) {
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
      setSuccess("Cohort created.");
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
    <form onSubmit={handleSubmit} className="panel-soft space-y-5">
      <div className="space-y-2">
        <p className="eyebrow">Create a cohort</p>
        <h3 className="text-xl font-semibold text-[color:var(--text-strong)]">Start a fresh taste circle from one Letterboxd handle.</h3>
        <p className="text-sm leading-7 text-[color:var(--text-muted)]">
          Give the cohort a clear label, seed it from a profile, and let Kinoboxd build the ranking board around that
          network.
        </p>
      </div>

      <div className="space-y-2">
        <label htmlFor="seed-username" className="field-label">
          Seed username
        </label>
        <input
          id="seed-username"
          className="field-input"
          value={seedUsername}
          onChange={(event) => setSeedUsername(event.target.value)}
          placeholder="letterboxd_user"
          required
        />
      </div>

      <div className="space-y-2">
        <label htmlFor="cohort-label" className="field-label">
          Cohort label
        </label>
        <input
          id="cohort-label"
          className="field-input"
          value={label}
          onChange={(event) => setLabel(event.target.value)}
          placeholder="Weekend repertory crew"
          required
        />
      </div>

      <button
        type="submit"
        className="button-primary w-full disabled:cursor-not-allowed disabled:opacity-60"
        disabled={isSubmitting || isRefreshing}
      >
        {isSubmitting ? "Creating..." : isRefreshing ? "Refreshing..." : "Create cohort"}
      </button>
      {error ? <p className="text-sm text-red-300">{error}</p> : null}
      {success ? <p className="text-sm text-emerald-300">{success}</p> : null}
    </form>
  );
}

export function CreateCohortForm({ onCreated }: { onCreated?: () => void }) {
  if (isDemoMode) {
    return <DemoLockedNotice />;
  }
  return <CreateCohortFormInner onCreated={onCreated} />;
}
