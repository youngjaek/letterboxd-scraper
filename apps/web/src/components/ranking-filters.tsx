"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState, useTransition } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useSearchParamsUpdater, useSyncedSearchParams } from "./search-params-provider";
import { getApiBase } from "@/lib/api-base";

type Option = {
  value: string;
  label: string;
  hint?: string | null;
};

const apiBase = getApiBase();
const distributionOptions: Option[] = [
  { value: "five-star-dominant", label: "5★ Dominant", hint: "40%+ 5★, clear lead" },
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
  const searchParams = useSyncedSearchParams();
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<Option[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const selectedValues = useMemo(() => searchParams.getAll(paramKey), [searchParams, paramKey]);
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
          setHighlightedIndex(filtered.length > 0 ? 0 : -1);
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setSuggestions([]);
        }
      });
    return () => controller.abort();
  }, [query, endpoint, mapResponse, selectedValues]);

  useEffect(() => {
    if (!showSuggestions) {
      setHighlightedIndex(-1);
    }
  }, [showSuggestions]);

  function updateParams(mutator: (params: URLSearchParams) => void) {
    const params = new URLSearchParams(searchParams.toString());
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
    setHighlightedIndex(-1);
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
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") {
              event.preventDefault();
              if (!suggestions.length) {
                return;
              }
              setShowSuggestions(true);
              setHighlightedIndex((prev) => {
                const next = prev + 1;
                if (next >= suggestions.length) {
                  return 0;
                }
                return next;
              });
              return;
            }
            if (event.key === "ArrowUp") {
              event.preventDefault();
              if (!suggestions.length) {
                return;
              }
              setShowSuggestions(true);
              setHighlightedIndex((prev) => {
                if (prev <= 0) {
                  return suggestions.length - 1;
                }
                return prev - 1;
              });
              return;
            }
            if (event.key === "Enter") {
              if (highlightedIndex >= 0 && highlightedIndex < suggestions.length) {
                event.preventDefault();
                addOption(suggestions[highlightedIndex]);
              }
              return;
            }
            if (event.key === "Escape") {
              setShowSuggestions(false);
              setHighlightedIndex(-1);
            }
          }}
          onFocus={() => setShowSuggestions(true)}
          onBlur={() => {
            setTimeout(() => setShowSuggestions(false), 150);
          }}
          placeholder={placeholder}
          className="w-full rounded border border-white/10 bg-black/40 px-3 py-2 text-sm text-white focus:border-brand-primary focus:outline-none"
        />
        {showSuggestions && suggestions.length > 0 && (
          <ul className="absolute z-10 mt-1 max-h-48 w-full overflow-auto rounded border border-white/10 bg-slate-900/90 text-sm text-white shadow">
            {suggestions.map((option, index) => (
              <li
                key={option.value}
                className={`cursor-pointer px-3 py-2 ${highlightedIndex === index ? "bg-white/20 text-white" : "hover:bg-white/10"}`}
                onMouseDown={(event) => event.preventDefault()}
                onMouseEnter={() => setHighlightedIndex(index)}
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

function normalizeWatchersToken(token: string) {
  const cleaned = token.replace(/,/g, "").trim();
  if (!cleaned) {
    return "";
  }
  return /^\d+$/.test(cleaned) ? cleaned : "";
}

function parseWatchersRange(value: string) {
  const trimmed = value.trim();
  if (!trimmed) {
    return { min: "", max: "" };
  }
  if (!trimmed.includes("..")) {
    const normalized = normalizeWatchersToken(trimmed);
    return normalized ? { min: normalized, max: normalized } : { min: "", max: "" };
  }
  const [startRaw = "", endRaw = ""] = trimmed.split("..");
  return {
    min: normalizeWatchersToken(startRaw),
    max: normalizeWatchersToken(endRaw),
  };
}

function formatWatchersValue(value: string) {
  if (!value) {
    return "";
  }
  const num = Number(value);
  if (Number.isNaN(num)) {
    return value;
  }
  return num.toLocaleString();
}

function formatWatchersRange(min: string, max: string) {
  const formattedMin = formatWatchersValue(min);
  const formattedMax = formatWatchersValue(max);
  if (formattedMin && formattedMax) {
    return formattedMin === formattedMax ? formattedMin : `${formattedMin}..${formattedMax}`;
  }
  if (formattedMin) {
    return `${formattedMin}..`;
  }
  if (formattedMax) {
    return `..${formattedMax}`;
  }
  return "";
}

function ReleaseYearFilters() {
  const searchParams = useSyncedSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const minRaw = searchParams.get("release_year_min") ?? "";
  const maxRaw = searchParams.get("release_year_max") ?? "";
  const decadeRaw = searchParams.get("decade") ?? "";
  const computedRangeValue = useMemo(() => formatReleaseYearRange(minRaw, maxRaw), [minRaw, maxRaw]);
  const [rangeValue, setRangeValue] = useState(computedRangeValue);

  useEffect(() => setRangeValue(computedRangeValue), [computedRangeValue]);

  function commitRange(value: string) {
    const params = new URLSearchParams(searchParams.toString());
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
    const params = new URLSearchParams(searchParams.toString());
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
  const searchParams = useSyncedSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const selectedValue = searchParams.get("distribution") ?? "";
  const [pendingValue, setPendingValue] = useState<string | null>(null);
  const updateParams = useSearchParamsUpdater();

  const handleChange = useCallback(
    (value: string) => {
      setPendingValue(value);
      let nextQuery = "";
      updateParams(
        (params) => {
          if (value) {
            params.set("distribution", value);
          } else {
            params.delete("distribution");
          }
          params.delete("page");
          nextQuery = params.toString();
        },
        { updateHistory: false },
      );
      router.push(nextQuery ? `${pathname}?${nextQuery}` : pathname, { scroll: false });
    },
    [pathname, router, updateParams],
  );

  useEffect(() => {
    setPendingValue(null);
  }, [selectedValue]);

  return (
    <div className="flex flex-col gap-2">
      <span className="text-[0.6rem] font-semibold uppercase tracking-[0.2em] text-slate-400">
        Distribution
      </span>
      <label className="flex flex-col gap-1 text-xs text-slate-400">
        <span>Filter by cluster</span>
        <select
          className="w-48 rounded border border-white/10 bg-black/40 px-3 py-2 text-sm text-white focus:border-brand-primary focus:outline-none"
          value={pendingValue ?? selectedValue}
          onChange={(event) => handleChange(event.target.value)}
        >
          <option value="">Any distribution</option>
          {distributionOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}

function WatchersFilters() {
  const searchParams = useSyncedSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const minRaw = searchParams.get("watchers_min") ?? "";
  const maxRaw = searchParams.get("watchers_max") ?? "";
  const computedRangeValue = useMemo(
    () => formatWatchersRange(minRaw, maxRaw),
    [minRaw, maxRaw],
  );
  const [rangeValue, setRangeValue] = useState(computedRangeValue);

  useEffect(() => setRangeValue(computedRangeValue), [computedRangeValue]);

  function commitRange(value: string) {
    const params = new URLSearchParams(searchParams.toString());
    const parsed = parseWatchersRange(value);
    let minValue = parsed.min;
    let maxValue = parsed.max;
    if (minValue && maxValue) {
      const minNum = parseInt(minValue, 10);
      const maxNum = parseInt(maxValue, 10);
      if (!Number.isNaN(minNum) && !Number.isNaN(maxNum) && minNum > maxNum) {
        minValue = String(maxNum);
        maxValue = String(minNum);
      }
    }
    if (minValue) {
      params.set("watchers_min", minValue);
    } else {
      params.delete("watchers_min");
    }
    if (maxValue) {
      params.set("watchers_max", maxValue);
    } else {
      params.delete("watchers_max");
    }
    params.delete("page");
    const formatted = formatWatchersRange(minValue, maxValue);
    setRangeValue(formatted);
    const query = params.toString();
    router.push(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }

  return (
    <div className="flex flex-col gap-2">
      <span className="text-[0.6rem] font-semibold uppercase tracking-[0.2em] text-slate-400">
        Watchers
      </span>
      <div className="flex flex-wrap gap-3 text-xs text-slate-400">
        <label className="flex flex-col gap-1">
          <span>Count / Range</span>
          <input
            type="text"
            value={rangeValue}
            placeholder="50 or 50..500"
            onChange={(event) => setRangeValue(event.target.value)}
            onBlur={() => commitRange(rangeValue)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                commitRange(rangeValue);
              }
            }}
            className="w-48 rounded border border-white/10 bg-black/40 px-3 py-2 text-sm text-white focus:border-brand-primary focus:outline-none"
          />
        </label>
      </div>
    </div>
  );
}

function LetterboxdSourceFilter() {
  const searchParams = useSyncedSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const appliedValue = searchParams.get("letterboxd_source") ?? "";
  const [value, setValue] = useState(appliedValue);
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    setValue(appliedValue);
  }, [appliedValue]);

  function updateFilter(nextValue: string) {
    const params = new URLSearchParams(searchParams.toString());
    const trimmed = nextValue.trim();
    if (trimmed) {
      params.set("letterboxd_source", trimmed);
    } else {
      params.delete("letterboxd_source");
    }
    params.delete("page");
    const query = params.toString();
    startTransition(() => {
      router.push(query ? `${pathname}?${query}` : pathname, { scroll: false });
    });
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    updateFilter(value);
  }

  function clearValue() {
    if (!appliedValue) {
      setValue("");
      return;
    }
    setValue("");
    updateFilter("");
  }

  return (
    <div className="flex flex-col gap-2">
      <span className="text-[0.6rem] font-semibold uppercase tracking-[0.2em] text-slate-400">
        Letterboxd List / Filmography
      </span>
      <form
        onSubmit={handleSubmit}
        className="flex flex-col gap-3 text-xs text-slate-400 md:flex-row md:items-end"
      >
        <label className="flex flex-1 flex-col gap-1">
          <span>Paste URL or boxd.it link</span>
          <input
            type="text"
            value={value}
            placeholder="https://letterboxd.com/..."
            onChange={(event) => setValue(event.target.value)}
            className="w-full rounded border border-white/10 bg-black/40 px-3 py-2 text-sm text-white focus:border-brand-primary focus:outline-none"
          />
        </label>
        <div className="flex items-center gap-2">
          <button
            type="submit"
            disabled={isPending}
            className="rounded border border-brand-primary/60 bg-brand-primary/10 px-4 py-2 text-[0.6rem] uppercase tracking-[0.2em] text-white transition hover:border-brand-primary hover:bg-brand-primary/20 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isPending ? "Applying…" : "Apply"}
          </button>
          <button
            type="button"
            onClick={clearValue}
            disabled={isPending}
            className="rounded border border-white/15 px-3 py-2 text-[0.6rem] uppercase tracking-[0.2em] text-white/80 hover:border-white/30 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            Clear
          </button>
        </div>
      </form>
      <p className="text-[0.65rem] text-slate-500">
        Works with Letterboxd lists, short <span className="text-white/70">boxd.it</span> links, or filmography pages.
        Results show only films present in the provided source.
      </p>
      {appliedValue ? (
        <p className="text-[0.65rem] text-slate-400">
          Filtering by <span className="font-mono text-white/80">{appliedValue}</span>
        </p>
      ) : null}
    </div>
  );
}

export function RankingFilters() {
  const searchParams = useSyncedSearchParams();
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
    "watchers_min",
    "watchers_max",
    "letterboxd_source",
  ];
  const hasFilters = filterKeys.some((key) => searchParams.getAll(key).length > 0);
  const mapGenre = useCallback((item: any) => ({ value: String(item.id), label: item.name }), []);
  const mapCountry = useCallback(
    (item: any) => ({ value: item.code, label: item.name ?? item.code }),
    [],
  );
  const mapDirector = useCallback((item: any) => ({ value: String(item.id), label: item.name }), []);

  function clearFilters() {
    const params = new URLSearchParams(searchParams.toString());
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
        <div className="grid gap-4 md:grid-cols-2">
          <ReleaseYearFilters />
          <WatchersFilters />
        </div>
        <LetterboxdSourceFilter />
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
