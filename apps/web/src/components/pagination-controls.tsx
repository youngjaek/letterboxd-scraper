"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

export function PaginationControls({ page, totalPages }: { page: number; totalPages: number }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  function setPage(next: number) {
    const params = new URLSearchParams(searchParams?.toString() ?? "");
    if (next <= 1) {
      params.delete("page");
    } else {
      params.set("page", String(next));
    }
    const query = params.toString();
    router.push(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }

  return (
    <div className="flex items-center justify-between border-t border-white/10 px-6 py-4 text-sm text-slate-300">
      <button
        type="button"
        onClick={() => setPage(page - 1)}
        disabled={page <= 1}
        className="rounded border border-white/20 px-3 py-1 disabled:cursor-not-allowed disabled:opacity-40"
      >
        Previous
      </button>
      <span className="text-xs uppercase tracking-[0.2em] text-slate-400">
        Page {page} of {totalPages}
      </span>
      <button
        type="button"
        onClick={() => setPage(page + 1)}
        disabled={page >= totalPages}
        className="rounded border border-white/20 px-3 py-1 disabled:cursor-not-allowed disabled:opacity-40"
      >
        Next
      </button>
    </div>
  );
}
