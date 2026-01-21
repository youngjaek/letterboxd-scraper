"use client";

import { useCallback, useEffect, useMemo, useRef, useState, useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { getApiBase } from "@/lib/api-base";

type Option = {
  value: string;
  label: string;
  hint?: string | null;
};

const apiBase = getApiBase();
const distributionOptions: Option[] = [
  { value: "strong-left", label: "Strong Left", hint: "4½★ spikes" },
  { value: "left", label: "Left Skew", hint: "≥60% ≥4★" },
  { value: "balanced", label: "Balanced", hint: "3–4★ bulk" },
  { value: "bimodal-low-high", label: "Bimodal ±", hint: "Love vs hate" },
  { value: "bimodal-mid", label: "Bimodal Mid", hint: "Middle hump" },
  { value: "right", label: "Right Skew", hint: "Low-star heavy" },
  { value: "mixed", label: "Mixed", hint: "No clear skew" },
  { value: "unknown", label: "Unknown", hint: "No data" },
];

function useSelectedOptions(
  values: string[],
  endpoint: string,
  idParam: string,
  mapResponse: (item: any) => Option,
) {
  const [options, setOptions] = useState<Option[]>([]);
  useEffect(() => {
    if (!values.length) {
      setOptions([]);
      return;
    }
    const controller = new AbortController();
    const url = new URL(`${apiBase}${endpoint}`);
    values.forEach((value) => url.searchParams.append(idParam, value));
    fetch(url.toString(), { signal: controller.signal })
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => setOptions((data || []).map(mapResponse)))
      .catch(() => {
        if (!controller.signal.aborted) {
          setOptions([]);
        }
      });
    return () => controller.abort();
  }, [values.join(","), endpoint, idParam, mapResponse]);
  return options;
}

function MultiSelectFilter({
  label,
  placeholder,
  endpoint,
  paramKey,
  idParam,
  mapResponse,
}: {
  label: string;
  placeholder: string;
  endpoint: string;
  paramKey: string;
  idParam: string;
  mapResponse: (item: any) => Option;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<Option[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const selectedValues = useMemo(() => searchParams?.getAll(paramKey) ?? [], [searchParams, paramKey]);
  const selectedOptions = useSelectedOptions(selectedValues, endpoint, idParam, mapResponse);

  useEffect(() => {
    if (!query || query.trim().length < 2) {
      setSuggestions([]);
      return;
    }
    const controller = new AbortController();
    const url = new URL(`${apiBase}${endpoint}`);
    url.searchParams.set("q", query.trim());
    url.searchParams.set("limit", "8");
    fetch(url.toString(), { signal: controller.signal })
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => {
        if (!controller.signal.aborted) {
          const mapped = (data || []).map(mapResponse);
          const filtered = mapped.filter((option) => !selectedValues.includes(option.value));
          setSuggestions(filtered);
          setShowSuggestions(true);
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setSuggestions([]);
        }
      });
    return () => controller.abort();
  }, [query, endpoint, mapResponse, selectedValues]);

  function updateParams(mutator: (params: URLSearchParams) => void) {
    const params = new URLSearchParams(searchParams?.toString() ?? "");
    mutator(params);
    params.delete("page");
    const queryString = params.toString();
    router.push(queryString ? `${pathname}?${queryString}` : pathname, { scroll: false });
  }

  function addOption(option: Option) {
    updateParams((params) => {
      params.append(paramKey, option.value);
    });
    setQuery("");
    setSuggestions([]);
    setShowSuggestions(false);
  }

  function removeValue(value: string) {
    updateParams((params) => {
      const remaining = selectedValues.filter((entry) => entry !== value);
      params.delete(paramKey);
      remaining.forEach((entry) => params.append(paramKey, entry));
    });
  }

  return (
    <div className="flex flex-1 flex-col gap-2">
      <label className="text-[0.6rem] font-semibold uppercase tracking-[0.2em] text-slate-400">
        {label}
      </label>
      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onFocus={() => setShowSuggestions(true)}
          onBlur={() => {
            setTimeout(() => setShowSuggestions(false), 150);
          }}
          placeholder={placeholder}
          className="w-full rounded border border-white/10 bg-black/40 px-3 py-2 text-sm text-white focus:border-brand-primary focus:outline-none"
        />
        {showSuggestions && suggestions.length > 0 && (
          <ul className="absolute z-10 mt-1 max-h-48 w-full overflow-auto rounded border border-white/10 bg-slate-900/90 text-sm text-white shadow">
            {suggestions.map((option) => (
              <li
                key={option.value}
                className="cursor-pointer px-3 py-2 hover:bg-white/10"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => addOption(option)}
              >
                <span className="font-semibold">{option.label}</span>
                {option.hint ? <span className="ml-2 text-xs text-slate-400">{option.hint}</span> : null}
              </li>
            ))}
          </ul>
        )}
      </div>
      {selectedOptions.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {selectedOptions.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => removeValue(option.value)}
              className="flex items-center gap-1 rounded-full border border-white/20 px-3 py-1 text-xs text-white hover:border-brand-primary"
            >
              {option.label}
              <span className="text-slate-400">×</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function formatReleaseYearRange(min: string, max: string) {
  if (min && max) {
    return min === max ? min : `${min}..${max}`;
  }
  if (min) {
    return `${min}..`;
  }
  if (max) {
    return `..${max}`;
  }
  return "";
}

function normalizeYearToken(token: string) {
  const trimmed = token.trim();
  if (!trimmed) {
    return "";
  }
  return /^\d{4}$/.test(trimmed) ? trimmed : "";
}

function parseReleaseYearRange(value: string) {
  const trimmed = value.trim();
  if (!trimmed) {
    return { min: "", max: "" };
  }
  if (!trimmed.includes("..")) {
    const year = normalizeYearToken(trimmed);
    return year ? { min: year, max: year } : { min: "", max: "" };
  }
  const [startRaw = "", endRaw = ""] = trimmed.split("..");
  const min = normalizeYearToken(startRaw);
  const max = normalizeYearToken(endRaw);
  return { min, max };
}

function ReleaseYearFilters() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const minRaw = searchParams?.get("release_year_min") ?? "";
  const maxRaw = searchParams?.get("release_year_max") ?? "";
  const decadeRaw = searchParams?.get("decade") ?? "";
  const computedRangeValue = useMemo(() => formatReleaseYearRange(minRaw, maxRaw), [minRaw, maxRaw]);
  const [rangeValue, setRangeValue] = useState(computedRangeValue);

  useEffect(() => setRangeValue(computedRangeValue), [computedRangeValue]);

  function commitRange(value: string) {
    const params = new URLSearchParams(searchParams?.toString() ?? "");
    const parsed = parseReleaseYearRange(value);
    if (parsed.min) {
      params.set("release_year_min", parsed.min);
    } else {
      params.delete("release_year_min");
    }
    if (parsed.max) {
      params.set("release_year_max", parsed.max);
    } else {
      params.delete("release_year_max");
    }
    setRangeValue(formatReleaseYearRange(parsed.min, parsed.max));
    params.delete("page");
    const query = params.toString();
    router.push(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }

  function setDecade(value: string) {
    const params = new URLSearchParams(searchParams?.toString() ?? "");
    if (value) {
      params.set("decade", value);
    } else {
      params.delete("decade");
    }
    params.delete("page");
    const query = params.toString();
    router.push(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }

  const decades = Array.from({ length: 14 }).map((_, index) => 1900 + index * 10);

  return (
    <div className="flex flex-col gap-2">
      <span className="text-[0.6rem] font-semibold uppercase tracking-[0.2em] text-slate-400">
        Release Year
      </span>
      <div className="flex flex-wrap gap-3 text-xs text-slate-400">
        <label className="flex flex-col gap-1">
          <span>Year / Range</span>
          <input
            type="text"
            value={rangeValue}
            placeholder="1954 or 1920..1954"
            onChange={(event) => setRangeValue(event.target.value)}
            onBlur={() => commitRange(rangeValue)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                commitRange(rangeValue);
              }
            }}
            className="w-40 rounded border border-white/10 bg-black/40 px-3 py-2 text-sm text-white focus:border-brand-primary focus:outline-none"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span>Decade</span>
          <select
            value={decadeRaw}
            onChange={(event) => setDecade(event.target.value)}
            className="w-40 rounded border border-white/10 bg-black/40 px-3 py-2 text-sm text-white focus:border-brand-primary focus:outline-none"
          >
            <option value="">Any</option>
            {decades.map((decade) => (
              <option key={decade} value={decade}>
                {decade}s
              </option>
            ))}
          </select>
        </label>
      </div>
    </div>
  );
}

function DistributionFilter() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const selectedValue = searchParams?.get("distribution") ?? "";
  const [optimisticValue, setOptimisticValue] = useState<string | undefined>();
  const [isPending, startTransition] = useTransition();
  const activeValue = optimisticValue ?? selectedValue;
  const prefetchedUrls = useRef<Set<string>>(new Set());
  const prefetchedAll = useRef(false);

  useEffect(() => {
    setOptimisticValue(undefined);
  }, [selectedValue]);

  const buildUrl = useCallback(
    (value: string) => {
      const params = new URLSearchParams(searchParams?.toString() ?? "");
      if (value) {
        params.set("distribution", value);
      } else {
        params.delete("distribution");
      }
      params.delete("page");
      const query = params.toString();
      return query ? `${pathname}?${query}` : pathname;
    },
    [searchParams, pathname],
  );

  const prefetchUrl = useCallback(
    (url: string) => {
      if (prefetchedUrls.current.has(url)) {
        return;
      }
      prefetchedUrls.current.add(url);
      router.prefetch(url);
    },
    [router],
  );

  const ensurePrefetchAll = useCallback(() => {
    if (prefetchedAll.current) {
      return;
    }
    prefetchedAll.current = true;
    const targets = ["", ...distributionOptions.map((option) => option.value)];
    targets.forEach((value) => prefetchUrl(buildUrl(value)));
  }, [buildUrl, prefetchUrl]);

  function toggle(value: string) {
    ensurePrefetchAll();
    const nextValue = activeValue === value ? "" : value;
    setOptimisticValue(nextValue);
    startTransition(() => {
      const url = buildUrl(nextValue);
      router.push(url, { scroll: false });
    });
  }

  function handlePrefetch(value: string) {
    ensurePrefetchAll();
    const nextValue = activeValue === value ? "" : value;
    prefetchUrl(buildUrl(nextValue));
  }

  return (
    <div
      className="flex flex-col gap-2"
      onMouseEnter={ensurePrefetchAll}
      onFocusCapture={ensurePrefetchAll}
      onTouchStart={ensurePrefetchAll}
    >
      <span className="text-[0.6rem] font-semibold uppercase tracking-[0.2em] text-slate-400">
        Distribution
      </span>
      <div className="flex flex-wrap gap-2">
        {distributionOptions.map((option) => {
          const isActive = activeValue === option.value;
          const baseClasses =
            "flex min-w-[120px] flex-1 flex-col rounded border px-3 py-2 text-left text-xs transition";
          const stateClasses = isActive
            ? "border-brand-primary bg-brand-primary/10 text-white"
            : "border-white/15 text-slate-200 hover:border-white/30 hover:text-white";
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => toggle(option.value)}
              onMouseEnter={() => handlePrefetch(option.value)}
              onFocus={() => handlePrefetch(option.value)}
              disabled={isPending && optimisticValue === option.value}
              className={`${baseClasses} ${stateClasses}`}
            >
              <span className="text-sm font-semibold">{option.label}</span>
              {option.hint ? (
                <span className="text-[0.6rem] uppercase tracking-[0.25em] text-slate-400">
                  {option.hint}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function RankingFilters() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const filterKeys = [
    "genres",
    "countries",
    "directors",
    "distribution",
    "release_year_min",
    "release_year_max",
    "decade",
  ];
  const hasFilters = filterKeys.some((key) => (searchParams?.getAll(key) ?? []).length > 0);
  const mapGenre = useCallback((item: any) => ({ value: String(item.id), label: item.name }), []);
  const mapCountry = useCallback(
    (item: any) => ({ value: item.code, label: item.name ?? item.code }),
    [],
  );
  const mapDirector = useCallback((item: any) => ({ value: String(item.id), label: item.name }), []);

  function clearFilters() {
    const params = new URLSearchParams(searchParams?.toString() ?? "");
    filterKeys.forEach((key) => params.delete(key));
    params.delete("page");
    const query = params.toString();
    router.push(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }

  return (
    <div className="border-b border-white/10 px-6 py-4">
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-4 lg:flex-row">
          <MultiSelectFilter
            label="Genres"
            placeholder="Search genres"
            endpoint="/filters/genres"
            paramKey="genres"
            idParam="ids"
            mapResponse={mapGenre}
          />
          <MultiSelectFilter
            label="Countries"
            placeholder="Search countries"
            endpoint="/filters/countries"
            paramKey="countries"
            idParam="codes"
            mapResponse={mapCountry}
          />
          <MultiSelectFilter
            label="Directors"
            placeholder="Search directors"
            endpoint="/filters/directors"
            paramKey="directors"
            idParam="ids"
            mapResponse={mapDirector}
          />
        </div>
        <ReleaseYearFilters />
        <DistributionFilter />
        <div className="flex justify-end">
          <button
            type="button"
            onClick={clearFilters}
            disabled={!hasFilters}
            className="rounded border border-white/20 px-3 py-2 text-xs uppercase tracking-[0.2em] text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            Clear filters
          </button>
        </div>
      </div>
    </div>
  );
}
