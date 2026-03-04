"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { PaginationControls } from "./pagination-controls";
import { RatingHistogram } from "./rating-histogram";
import { useSearchParamsUpdater, useSyncedSearchParams } from "./search-params-provider";
import { DEFAULT_PAGE_SIZE, DEFAULT_RESULT_LIMIT, PAGE_SIZE_OPTIONS } from "@/lib/ranking-options";
import { DEFAULT_RANKING_SORT, RANKING_SORT_OPTIONS, RankingSortOption } from "@/lib/ranking-sort";
import { RankingRow } from "@/types/ranking-row";

type RankingBrowserProps = {
  items: RankingRow[];
  totalItems: number;
  initialPage: number;
  initialPageSize: number;
  initialResultLimit: number;
  initialSortBy?: string;
  initialSortOrder?: string;
};

function getSortValue(sortBy?: string, sortOrder?: string) {
  if (!sortBy && !sortOrder) {
    return DEFAULT_RANKING_SORT.value;
  }
  const match = RANKING_SORT_OPTIONS.find(
    (option) =>
      option.sortBy === (sortBy ?? DEFAULT_RANKING_SORT.sortBy) &&
      option.sortOrder === (sortOrder ?? DEFAULT_RANKING_SORT.sortOrder),
  );
  return match ? match.value : DEFAULT_RANKING_SORT.value;
}

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "—";
  }
  return `${Math.round(value * 100)}%`;
}

function formatAverage(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "—";
  }
  return value.toFixed(2);
}

function letterboxdUrl(slug: string) {
  return `https://letterboxd.com/film/${slug}/`;
}

function StatPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col rounded-md border border-white/10 bg-black/40 px-3 py-1 text-xs text-white/90">
      <span className="text-[0.55rem] uppercase tracking-[0.3em] text-slate-400">{label}</span>
      <span className="text-sm font-semibold text-white">{value}</span>
    </div>
  );
}

function compareValues(
  a: number | null | undefined,
  b: number | null | undefined,
  order: "asc" | "desc",
) {
  const fallback = order === "asc" ? Number.POSITIVE_INFINITY : Number.NEGATIVE_INFINITY;
  const first = typeof a === "number" ? a : fallback;
  const second = typeof b === "number" ? b : fallback;
  return order === "asc" ? first - second : second - first;
}

function sortItems(items: RankingRow[], option: RankingSortOption) {
  return [...items].sort((a, b) => {
    switch (option.sortBy) {
      case "watchers":
        return compareValues(a.watchers, b.watchers, option.sortOrder);
      case "release_year":
        return compareValues(a.release_year, b.release_year, option.sortOrder);
      case "avg_rating":
        return compareValues(a.avg_rating, b.avg_rating, option.sortOrder);
      case "score":
      default:
        return compareValues(a.score, b.score, option.sortOrder);
    }
  });
}

export function RankingBrowser({
  items,
  totalItems,
  initialPage,
  initialPageSize,
  initialResultLimit,
  initialSortBy,
  initialSortOrder,
}: RankingBrowserProps) {
  const router = useRouter();
  const pathname = usePathname();
  const syncedSearchParams = useSyncedSearchParams();
  const updateSearchParams = useSearchParamsUpdater();
  const [page, setPage] = useState(initialPage);
  const [pageSize, setPageSize] = useState(initialPageSize);
  const [resultLimit, setResultLimit] = useState(initialResultLimit);
  const [sortValue, setSortValue] = useState(getSortValue(initialSortBy, initialSortOrder));

  useEffect(() => {
    setPage(initialPage);
  }, [initialPage]);

  useEffect(() => {
    setPageSize(initialPageSize);
  }, [initialPageSize]);

  useEffect(() => {
    setResultLimit(initialResultLimit);
  }, [initialResultLimit]);

  useEffect(() => {
    setSortValue(getSortValue(initialSortBy, initialSortOrder));
  }, [initialSortBy, initialSortOrder]);

  const selectedSortOption =
    RANKING_SORT_OPTIONS.find((option) => option.value === sortValue) ?? DEFAULT_RANKING_SORT;

  const activeDistribution = syncedSearchParams.get("distribution") ?? "";

  const filteredItems = useMemo(() => {
    if (!activeDistribution) {
      return items;
    }
    return items.filter((item) => item.distribution_label === activeDistribution);
  }, [activeDistribution, items]);

  const filteredTotal = filteredItems.length;
  const sortedItems = useMemo(
    () => sortItems(filteredItems, selectedSortOption),
    [filteredItems, selectedSortOption],
  );

  const totalPages = Math.max(1, Math.ceil(Math.max(filteredTotal, 1) / pageSize));
  const totalMatchingItems = activeDistribution ? filteredTotal : totalItems;

  useEffect(() => {
    setPage((current) => {
      if (current > totalPages) {
        const clamped = totalPages;
        updateSearchParams((params) => {
          if (clamped <= 1) {
            params.delete("page");
          } else {
            params.set("page", String(clamped));
          }
        });
        return clamped;
      }
      return current;
    });
  }, [totalPages, updateSearchParams]);

  const startIndex = (page - 1) * pageSize;
  const visibleItems = sortedItems.slice(startIndex, startIndex + pageSize);

  function handlePageChange(nextPage: number) {
    setPage(nextPage);
    updateSearchParams((params) => {
      if (nextPage <= 1) {
        params.delete("page");
      } else {
        params.set("page", String(nextPage));
      }
    });
  }

  function handlePageSizeChange(nextSize: number) {
    if (!PAGE_SIZE_OPTIONS.includes(nextSize as (typeof PAGE_SIZE_OPTIONS)[number])) {
      return;
    }
    setPageSize(nextSize);
    setPage(1);
    updateSearchParams((params) => {
      if (nextSize === DEFAULT_PAGE_SIZE) {
        params.delete("limit");
      } else {
        params.set("limit", String(nextSize));
      }
      params.delete("page");
    });
  }

  function handleSortChange(nextValue: string) {
    setSortValue(nextValue);
    setPage(1);
    const option =
      RANKING_SORT_OPTIONS.find((candidate) => candidate.value === nextValue) ?? DEFAULT_RANKING_SORT;
    updateSearchParams((params) => {
      if (option.sortBy === DEFAULT_RANKING_SORT.sortBy) {
        params.delete("sort_by");
      } else {
        params.set("sort_by", option.sortBy);
      }
      if (option.sortOrder === DEFAULT_RANKING_SORT.sortOrder) {
        params.delete("sort_order");
      } else {
        params.set("sort_order", option.sortOrder);
      }
      params.delete("page");
    });
  }

  function handleResultLimitChange(nextLimit: number) {
    if (nextLimit === resultLimit) {
      return;
    }
    setResultLimit(nextLimit);
    setPage(1);
    const params = new URLSearchParams(syncedSearchParams.toString());
    if (nextLimit === DEFAULT_RESULT_LIMIT) {
      params.delete("result_limit");
    } else {
      params.set("result_limit", String(nextLimit));
    }
    params.delete("page");
    const query = params.toString();
    const href = query ? `${pathname}?${query}` : pathname;
    router.push(href, { scroll: false });
  }

  return (
    <div className="rounded-xl border border-white/10 bg-white/5">
      <PaginationControls
        placement="top"
        page={page}
        totalPages={totalPages}
        totalItems={totalMatchingItems}
        pageSize={pageSize}
        resultLimit={resultLimit}
        sortValue={selectedSortOption.value}
        sortOptions={RANKING_SORT_OPTIONS}
        onPageChange={handlePageChange}
        onPageSizeChange={handlePageSizeChange}
        onResultLimitChange={handleResultLimitChange}
        onSortChange={handleSortChange}
      />
      {visibleItems.length === 0 ? (
        <p className="p-6 text-sm text-slate-400">No rankings found for the current filters.</p>
      ) : (
        <ol>
          {visibleItems.map((item) => {
            const directorNames = item.directors?.map((director) => director.name).filter(Boolean) ?? [];
            const primaryDirectors = directorNames.slice(0, 2);
            const extraDirectors = Math.max(0, directorNames.length - primaryDirectors.length);
            const genreTags = item.genres ? item.genres.slice(0, 3) : [];
            const metadataLine = item.release_year || primaryDirectors.length > 0;
            return (
              <li key={item.film_id} className="border-b border-white/5 px-6 py-5 last:border-b-0">
                <div className="grid gap-4 sm:grid-cols-[120px,1fr]">
                  <div className="max-w-[120px]">
                    <div className="overflow-hidden rounded-lg border border-white/10 bg-black/20">
                      {item.poster_url ? (
                        <Image
                          src={item.poster_url}
                          alt={`${item.title} poster`}
                          width={240}
                          height={360}
                          className="h-full w-full object-cover"
                          loading="lazy"
                          unoptimized
                        />
                      ) : (
                        <div className="flex aspect-[2/3] items-center justify-center text-xs text-slate-500">
                          No poster
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_220px] md:items-start">
                    <div className="flex h-full flex-col gap-3">
                      <div className="space-y-1">
                        <p className="text-sm uppercase tracking-[0.3em] text-brand-accent">
                          #{item.rank ?? "?"}
                        </p>
                        <div className="flex flex-wrap items-baseline gap-2">
                          <Link
                            href={letterboxdUrl(item.slug)}
                            target="_blank"
                            className="text-xl font-semibold text-white hover:text-brand-primary"
                          >
                            {item.title}
                          </Link>
                          {metadataLine ? (
                            <span className="text-sm text-slate-300">
                              {item.release_year ? `(${item.release_year})` : ""}
                              {item.release_year && primaryDirectors.length ? " " : ""}
                              {primaryDirectors.length
                                ? `by ${primaryDirectors.join(", ")}${
                                    extraDirectors > 0 ? ` +${extraDirectors} more` : ""
                                  }`
                                : ""}
                            </span>
                          ) : null}
                        </div>
                      </div>
                      <p className="text-xs text-slate-500">{item.slug}</p>
                      <div className="min-h-[32px]">
                        {genreTags.length ? (
                          <div className="flex flex-wrap gap-1.5 text-[0.55rem] uppercase tracking-[0.25em] text-slate-400">
                            {genreTags.map((genre) => (
                              <span
                                key={genre}
                                className="rounded-full border border-white/15 px-2 py-0.5 text-slate-200/80"
                              >
                                {genre}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <div className="h-4" aria-hidden="true" />
                        )}
                      </div>
                      <div className="mt-auto flex flex-wrap items-end gap-3">
                        <StatPill label="Watchers" value={item.watchers?.toLocaleString() ?? "—"} />
                        <StatPill label="Avg" value={formatAverage(item.avg_rating)} />
                        <StatPill label="Fav %" value={formatPercent(item.favorite_rate)} />
                        <StatPill label="Like %" value={formatPercent(item.like_rate)} />
                        <StatPill
                          label="Consensus"
                          value={
                            item.consensus_strength !== null && item.consensus_strength !== undefined
                              ? item.consensus_strength.toFixed(2)
                              : "—"
                          }
                        />
                      </div>
                    </div>
                    <div className="flex h-full flex-col">
                      <div className="text-right text-xs uppercase text-slate-400">
                        <p className="font-semibold text-white">
                          Score <span className="text-brand-primary">{item.score.toFixed(3)}</span>
                        </p>
                        <p>Distribution {item.distribution_label ?? "mixed"}</p>
                      </div>
                      <div className="mt-auto w-full rounded-lg border border-white/10 bg-black/30 px-2 py-1">
                        {item.rating_histogram?.length ? (
                          <RatingHistogram bins={item.rating_histogram} watchers={item.watchers} />
                        ) : (
                          <div className="text-center text-[0.6rem] text-slate-500">No data</div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      )}
      <PaginationControls
        page={page}
        totalPages={totalPages}
        totalItems={filteredTotal}
        pageSize={pageSize}
        resultLimit={resultLimit}
        sortValue={selectedSortOption.value}
        sortOptions={RANKING_SORT_OPTIONS}
        onPageChange={handlePageChange}
        onPageSizeChange={handlePageSizeChange}
        onResultLimitChange={handleResultLimitChange}
        onSortChange={handleSortChange}
      />
    </div>
  );
}
