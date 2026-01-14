"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

type MemberProfile = {
  username: string;
  avatar_url?: string | null;
};

const PAGE_SIZE = 8;

export function CohortMembersPanel({ members }: { members: MemberProfile[] }) {
  const [page, setPage] = useState(0);
  const [open, setOpen] = useState(false);
  const totalPages = useMemo(() => Math.ceil(members.length / PAGE_SIZE), [members.length]);
  const start = page * PAGE_SIZE;
  const current = members.slice(start, start + PAGE_SIZE);

  function goPrev() {
    setPage((prev) => Math.max(0, prev - 1));
  }
  function goNext() {
    setPage((prev) => Math.min(totalPages - 1, prev + 1));
  }

  if (members.length === 0) {
    return <p className="text-sm text-slate-400">No members found.</p>;
  }

  return (
    <div className="space-y-3">
      <button
        type="button"
        className="flex w-full items-center justify-between rounded border border-white/10 bg-black/40 px-4 py-2 text-left text-sm font-semibold text-white"
        onClick={() => setOpen((value) => !value)}
      >
        <span>
          Members <span className="text-slate-400">({members.length})</span>
        </span>
        <span className="text-xs uppercase tracking-[0.3em] text-slate-400">{open ? "Hide" : "Show"}</span>
      </button>
      {open && (
        <div className="space-y-3">
          {totalPages > 1 && (
            <div className="flex items-center justify-between text-xs uppercase tracking-[0.3em] text-slate-400">
              <button
                type="button"
                className="rounded border border-white/20 px-2 py-1 text-white disabled:opacity-30"
                onClick={goPrev}
                disabled={page === 0}
              >
                Prev
              </button>
              <span>
                Page {page + 1}/{totalPages}
              </span>
              <button
                type="button"
                className="rounded border border-white/20 px-2 py-1 text-white disabled:opacity-30"
                onClick={goNext}
                disabled={page >= totalPages - 1}
              >
                Next
              </button>
            </div>
          )}
          <ul className="grid gap-2 text-sm text-slate-200 sm:grid-cols-2">
            {current.map((member) => (
              <li
                key={member.username}
                className="flex items-center gap-3 rounded-xl border border-white/5 bg-white/5 px-3 py-2 shadow-sm shadow-black/20"
              >
                {member.avatar_url ? (
                  <img
                    src={member.avatar_url}
                    alt={member.username}
                    className="h-8 w-8 rounded-full object-cover"
                    loading="lazy"
                  />
                ) : (
                  <div className="h-8 w-8 rounded-full bg-white/10 text-center text-[0.65rem] leading-8 text-white/70">
                    @{member.username[0]?.toUpperCase() ?? "?"}
                  </div>
                )}
                <div className="flex flex-col">
                  <Link
                    href={`https://letterboxd.com/${member.username}/`}
                    target="_blank"
                    className="font-mono text-xs uppercase tracking-wide text-brand-primary hover:text-brand-accent"
                  >
                    @{member.username}
                  </Link>
                  <span className="text-[0.65rem] uppercase tracking-[0.3em] text-slate-500">view profile</span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
