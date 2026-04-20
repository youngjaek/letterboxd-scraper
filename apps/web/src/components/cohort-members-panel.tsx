"use client";

import Image from "next/image";
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
    return <p className="text-sm text-[color:var(--text-muted)]">No members found.</p>;
  }

  return (
    <div className="panel-soft space-y-4">
      <button
        type="button"
        className="flex w-full items-center justify-between text-left"
        onClick={() => setOpen((value) => !value)}
      >
        <span>
          <p className="eyebrow">Members</p>
          <p className="mt-2 text-xl font-semibold text-[color:var(--text-strong)]">{members.length} people in this circle</p>
        </span>
        <span className="status-chip">{open ? "Hide" : "Show"}</span>
      </button>

      {open ? (
        <div className="space-y-4">
          {totalPages > 1 ? (
            <div className="flex items-center justify-between text-xs uppercase tracking-[0.24em] text-[color:var(--text-faint)]">
              <button type="button" className="button-ghost px-4 py-2 text-xs" onClick={goPrev} disabled={page === 0}>
                Prev
              </button>
              <span>
                Page {page + 1} of {totalPages}
              </span>
              <button
                type="button"
                className="button-ghost px-4 py-2 text-xs"
                onClick={goNext}
                disabled={page >= totalPages - 1}
              >
                Next
              </button>
            </div>
          ) : null}

          <ul className="grid gap-3 text-sm text-[color:var(--text-base)] sm:grid-cols-2">
            {current.map((member) => (
              <li
                key={member.username}
                className="flex items-center gap-3 rounded-[1.2rem] border border-white/5 bg-black/20 px-3 py-3"
              >
                {member.avatar_url ? (
                  <Image
                    src={member.avatar_url}
                    alt={member.username}
                    width={40}
                    height={40}
                    className="h-10 w-10 rounded-full object-cover"
                    loading="lazy"
                    unoptimized
                  />
                ) : (
                  <div className="flex h-10 w-10 items-center justify-center rounded-full bg-white/10 text-xs font-semibold uppercase text-[color:var(--text-strong)]">
                    {member.username[0]?.toUpperCase() ?? "?"}
                  </div>
                )}
                <div className="flex flex-col">
                  <a
                    href={`https://letterboxd.com/${member.username}/`}
                    target="_blank"
                    rel="noreferrer"
                    className="font-semibold text-[color:var(--text-strong)] transition hover:text-[color:var(--gold)]"
                  >
                    @{member.username}
                  </a>
                  <span className="text-[0.68rem] uppercase tracking-[0.22em] text-[color:var(--text-faint)]">
                    Letterboxd profile
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
