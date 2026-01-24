"use client";

import { FormEvent, useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  DEFAULT_PAGE_SIZE,
  DEFAULT_RESULT_LIMIT,
  PAGE_SIZE_OPTIONS,
  RESULT_LIMIT_OPTIONS,
} from "@/lib/ranking-options";

type PaginationControlsProps = {
  page: number;
  totalPages: number;
  totalItems: number;
  placement?: "top" | "bottom";
  pageSize: number;
  resultLimit: number;
};

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
  pageSize,
  resultLimit,
}: PaginationControlsProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [jumpValue, setJumpValue] = useState(String(page));
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [toastVisible, setToastVisible] = useState(false);
  useEffect(() => {
    if (!toastMessage) {
      setToastVisible(false);
      return undefined;
    }
    setToastVisible(true);
    const timeout = setTimeout(() => {
      setToastVisible(false);
      setTimeout(() => setToastMessage(null), 300);
    }, 2500);
    return () => clearTimeout(timeout);
  }, [toastMessage]);

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

  function updateParam(paramName: string, nextValue: number, defaultValue: number) {
    const params = new URLSearchParams(searchParams?.toString() ?? "");
    if (nextValue === defaultValue) {
      params.delete(paramName);
    } else {
      params.set(paramName, String(nextValue));
    }
    params.delete("page");
    const query = params.toString();
    router.push(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }

  function handleResultLimitChange(nextValue: number) {
    updateParam("result_limit", nextValue, DEFAULT_RESULT_LIMIT);
  }

  function handlePageSizeChange(nextValue: number) {
    updateParam("limit", nextValue, DEFAULT_PAGE_SIZE);
  }

  function submitJump(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsed = parseInt(jumpValue, 10);
    if (Number.isNaN(parsed)) {
      setJumpValue(String(page));
      setToastMessage("Enter a valid page number.");
      return;
    }
    if (parsed < 1 || parsed > totalPages) {
      setToastMessage(`Page must be between 1 and ${totalPages}.`);
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
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-[0.65rem] uppercase tracking-[0.2em] text-slate-400">{summary}</span>
        <div className="flex flex-wrap items-center gap-3 text-[0.65rem] uppercase tracking-[0.2em] text-slate-400">
          <label className="flex items-center gap-2">
            Top
            <select
              className="rounded border border-white/15 bg-black/30 px-2 py-1 text-[0.75rem] text-white focus:border-brand-primary focus:outline-none"
              value={resultLimit}
              onChange={(event) => handleResultLimitChange(Number(event.target.value))}
            >
              {RESULT_LIMIT_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2">
            Per page
            <select
              className="rounded border border-white/15 bg-black/30 px-2 py-1 text-[0.75rem] text-white focus:border-brand-primary focus:outline-none"
              value={pageSize}
              onChange={(event) => handlePageSizeChange(Number(event.target.value))}
            >
              {PAGE_SIZE_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <PaginationButton
          text="Prev"
          ariaLabel="Previous page"
          disabled={page <= 1}
          onClick={() => navigate(page - 1)}
        />
        <PaginationButton
          text="Next"
          ariaLabel="Next page"
          disabled={page >= totalPages}
          onClick={() => navigate(page + 1)}
        />
        <form onSubmit={submitJump} className="flex items-center gap-2">
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
      {toastMessage && (
        <div className="pointer-events-none fixed bottom-6 right-6">
          <span
            className={`rounded border border-black/10 bg-white px-4 py-2 text-xs text-black shadow-lg transition-opacity duration-300 ${
              toastVisible ? "opacity-100" : "opacity-0"
            }`}
          >
            {toastMessage}
          </span>
        </div>
      )}
    </div>
  );
}
