"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

type PaginationControlsProps = {
  page: number;
  totalPages: number;
  totalItems: number;
  placement?: "top" | "bottom";
};

type PageToken = number | "ellipsis";

function buildPageTokens(page: number, totalPages: number, siblingCount = 1): PageToken[] {
  if (totalPages <= 1) {
    return [1];
  }
  const totalNumbers = siblingCount * 2 + 5;
  if (totalNumbers >= totalPages) {
    return Array.from({ length: totalPages }, (_, idx) => idx + 1);
  }
  const leftSibling = Math.max(page - siblingCount, 1);
  const rightSibling = Math.min(page + siblingCount, totalPages);
  const showLeftEllipsis = leftSibling > 2;
  const showRightEllipsis = rightSibling < totalPages - 1;

  const items: PageToken[] = [1];

  if (showLeftEllipsis) {
    items.push("ellipsis");
  }

  const start = showLeftEllipsis ? leftSibling : 2;
  const end = showRightEllipsis ? rightSibling : totalPages - 1;
  for (let current = start; current <= end; current += 1) {
    items.push(current);
  }

  if (showRightEllipsis) {
    items.push("ellipsis");
  }

  if (totalPages > 1) {
    items.push(totalPages);
  }

  return items;
}

function PaginationButton({
  text,
  onClick,
  disabled = false,
  active = false,
  ariaLabel,
}: {
  text: string;
  onClick: () => void;
  disabled?: boolean;
  active?: boolean;
  ariaLabel?: string;
}) {
  const baseClasses =
    "rounded-full border px-3 py-1 text-xs transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-primary";
  const classes = active
    ? `${baseClasses} border-brand-primary bg-brand-primary/20 text-white`
    : `${baseClasses} border-white/20 text-slate-200 hover:border-brand-primary hover:text-white disabled:cursor-not-allowed disabled:opacity-40`;
  return (
    <button
      type="button"
      className={classes}
      disabled={disabled}
      onClick={onClick}
      aria-label={ariaLabel || text}
    >
      {text}
    </button>
  );
}

export function PaginationControls({
  page,
  totalPages,
  totalItems,
  placement = "bottom",
}: PaginationControlsProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [jumpValue, setJumpValue] = useState(String(page));
  const pageTokens = useMemo(() => buildPageTokens(page, totalPages), [page, totalPages]);

  useEffect(() => {
    setJumpValue(String(page));
  }, [page]);

  function clampPage(value: number) {
    if (!Number.isFinite(value)) {
      return page;
    }
    if (value < 1) {
      return 1;
    }
    if (value > totalPages) {
      return totalPages;
    }
    return value;
  }

  function navigate(next: number) {
    const target = clampPage(next);
    if (target === page) {
      return;
    }
    const params = new URLSearchParams(searchParams?.toString() ?? "");
    if (target <= 1) {
      params.delete("page");
    } else {
      params.set("page", String(target));
    }
    const query = params.toString();
    router.push(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }

  function handleJumpChange(value: string) {
    const numeric = value.replace(/[^0-9]/g, "");
    setJumpValue(numeric);
  }

  function submitJump(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsed = parseInt(jumpValue, 10);
    if (Number.isNaN(parsed)) {
      setJumpValue(String(page));
      return;
    }
    navigate(parsed);
  }

  const summary = `${totalItems.toLocaleString()} film${totalItems === 1 ? "" : "s"} · Page ${page} of ${totalPages}`;
  const containerClasses =
    placement === "top"
      ? "flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-6 py-3 text-xs text-slate-300"
      : "flex flex-wrap items-center justify-between gap-3 border-t border-white/10 px-6 py-4 text-xs text-slate-300";

  return (
    <div className={containerClasses}>
      <span className="text-[0.65rem] uppercase tracking-[0.2em] text-slate-400">{summary}</span>
      <div className="flex flex-wrap items-center gap-2">
        <PaginationButton text="First" ariaLabel="First page" disabled={page <= 1} onClick={() => navigate(1)} />
        <PaginationButton
          text="Prev"
          ariaLabel="Previous page"
          disabled={page <= 1}
          onClick={() => navigate(page - 1)}
        />
        <div className="flex flex-wrap items-center gap-1">
          {pageTokens.map((token, index) =>
            token === "ellipsis" ? (
              <span key={`ellipsis-${index}`} className="px-2 text-lg text-slate-500">
                …
              </span>
            ) : (
              <PaginationButton
                key={token}
                text={String(token)}
                ariaLabel={`Page ${token}`}
                active={token === page}
                onClick={() => navigate(token)}
              />
            ),
          )}
        </div>
        <PaginationButton
          text="Next"
          ariaLabel="Next page"
          disabled={page >= totalPages}
          onClick={() => navigate(page + 1)}
        />
        <PaginationButton
          text="Last"
          ariaLabel="Last page"
          disabled={page >= totalPages}
          onClick={() => navigate(totalPages)}
        />
        <form onSubmit={submitJump} className="ml-2 flex items-center gap-2">
          <label className="text-[0.55rem] uppercase tracking-[0.2em] text-slate-500">
            Go to
            <input
              type="text"
              inputMode="numeric"
              pattern="[0-9]*"
              value={jumpValue}
              onChange={(event) => handleJumpChange(event.target.value)}
              onBlur={() => {
                const parsed = parseInt(jumpValue, 10);
                if (Number.isNaN(parsed)) {
                  setJumpValue(String(page));
                  return;
                }
                const target = clampPage(parsed);
                setJumpValue(String(target));
              }}
              className="ml-2 w-16 rounded border border-white/15 bg-black/40 px-2 py-1 text-xs text-white placeholder:text-slate-500 focus:border-brand-primary focus:outline-none"
              placeholder="Page"
              aria-label="Go to page"
            />
          </label>
        </form>
      </div>
    </div>
  );
}
