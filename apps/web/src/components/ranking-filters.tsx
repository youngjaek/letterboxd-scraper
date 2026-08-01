"use client";

import type { Route } from "next";
import {
  FormEvent,
  KeyboardEvent as ReactKeyboardEvent,
  PointerEvent as ReactPointerEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useTransition,
} from "react";
import { usePathname, useRouter } from "next/navigation";
import { useSearchParamsUpdater, useSyncedSearchParams } from "./search-params-provider";
import { getApiBase } from "@/lib/api-base";

type Option = {
  value: string;
  label: string;
  hint?: string | null;
};

type GenreSearchResult = { id: number; name: string };
type CountrySearchResult = { code: string; name?: string | null };
type DirectorSearchResult = { id: number; name: string };
type MapResponseFn<T> = (item: T) => Option;

const apiBase = getApiBase();
const distributionOptions: Option[] = [
  { value: "masterpiece-consensus", label: "Universal acclaim", hint: "40%+ at 5★, almost no lows" },
  { value: "unclassified", label: "Unclassified", hint: "Doesn’t fit any pattern" },
];

function buildApiUrl(endpoint: string): URL {
  const absoluteBase = apiBase.startsWith("http://") || apiBase.startsWith("https://");
  if (absoluteBase) {
    return new URL(`${apiBase}${endpoint}`);
  }
  const origin =
    typeof window !== "undefined" && window.location?.origin
      ? window.location.origin
      : "http://127.0.0.1:3000";
  return new URL(`${apiBase}${endpoint}`, origin);
}

function DistributionSummary({ selectedValue }: { selectedValue: string }) {
  const active = distributionOptions.find((option) => option.value === selectedValue);
  if (!active) {
    return (
      <p className="text-[0.65rem] text-slate-500">
        Quickly narrow results by the overall histogram shape.
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-1 rounded border border-white/10 bg-black/30 px-3 py-2 text-[0.65rem] text-slate-200 sm:min-w-[13rem]">
      <span className="font-semibold text-white">{active.label}</span>
      {active.hint ? <span className="text-slate-400">{active.hint}</span> : null}
    </div>
  );
}

function useSelectedOptions<T>(
  values: string[],
  endpoint: string,
  idParam: string,
  mapResponse: MapResponseFn<T>,
) {
  const [options, setOptions] = useState<Option[]>([]);
  const valueSignature = values.join("|");
  useEffect(() => {
    if (!valueSignature) {
      setOptions([]);
      return;
    }
    const controller = new AbortController();
    const url = buildApiUrl(endpoint);
    valueSignature.split("|").forEach((value) => {
      if (value) {
        url.searchParams.append(idParam, value);
      }
    });
    fetch(url.toString(), { signal: controller.signal })
      .then(async (res) => (res.ok ? ((await res.json()) as T[]) : []))
      .then((data) => setOptions((data || []).map(mapResponse)))
      .catch(() => {
        if (!controller.signal.aborted) {
          setOptions([]);
        }
      });
    return () => controller.abort();
  }, [valueSignature, endpoint, idParam, mapResponse]);
  return options;
}

type MultiSelectFilterProps<T> = {
  label: string;
  placeholder: string;
  endpoint: string;
  paramKey: string;
  idParam: string;
  mapResponse: MapResponseFn<T>;
};

function MultiSelectFilter<T>({
  label,
  placeholder,
  endpoint,
  paramKey,
  idParam,
  mapResponse,
}: MultiSelectFilterProps<T>) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSyncedSearchParams();
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<Option[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const selectedValues = useMemo(() => searchParams.getAll(paramKey), [searchParams, paramKey]);
  const selectedOptions = useSelectedOptions<T>(selectedValues, endpoint, idParam, mapResponse);

  useEffect(() => {
    if (!query || query.trim().length < 2) {
      setSuggestions([]);
      return;
    }
    const controller = new AbortController();
    const url = buildApiUrl(endpoint);
    url.searchParams.set("q", query.trim());
    url.searchParams.set("limit", "8");
    fetch(url.toString(), { signal: controller.signal })
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => {
        if (!controller.signal.aborted) {
          const mapped = ((data || []) as T[]).map(mapResponse);
          const filtered = mapped.filter((option: Option) => !selectedValues.includes(option.value));
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
    const href = (queryString ? `${pathname}?${queryString}` : pathname) as Route;
    router.push(href, { scroll: false });
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
    const href = (query ? `${pathname}?${query}` : pathname) as Route;
    router.push(href, { scroll: false });
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
    const href = (query ? `${pathname}?${query}` : pathname) as Route;
    router.push(href, { scroll: false });
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

const RATING_SLIDER_MIN = 0.5;
const RATING_SLIDER_MAX = 5;
const RATING_SLIDER_STEP = 0.5;

function parseRatingValue(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed) || parsed < 0 || parsed > 5) {
    return null;
  }
  return parsed;
}

function formatRatingValue(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
}

function RatingRangeFilter() {
  const searchParams = useSyncedSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const manualMinRaw = searchParams.get("avg_rating_min") ?? "";
  const manualMaxRaw = searchParams.get("avg_rating_max") ?? "";
  const minInclusiveRaw = searchParams.get("avg_rating_min_inclusive");
  const maxInclusiveRaw = searchParams.get("avg_rating_max_inclusive");
  const sliderMinRaw = manualMinRaw;
  const sliderMaxRaw = manualMaxRaw;
  const [manualMin, setManualMin] = useState(manualMinRaw);
  const [manualMax, setManualMax] = useState(manualMaxRaw);
  const [minInclusive, setMinInclusive] = useState(minInclusiveRaw !== "false");
  const [maxInclusive, setMaxInclusive] = useState(maxInclusiveRaw !== "false");
  const [sliderMin, setSliderMin] = useState(
    parseRatingValue(sliderMinRaw ?? "") ?? RATING_SLIDER_MIN,
  );
  const [sliderMax, setSliderMax] = useState(
    parseRatingValue(sliderMaxRaw ?? "") ?? RATING_SLIDER_MAX,
  );
  const sliderValuesRef = useRef({ min: sliderMin, max: sliderMax });
  const draggingHandleRef = useRef<"min" | "max" | null>(null);
  const didDragRef = useRef(false);

  useEffect(() => {
    setManualMin(manualMinRaw);
    setManualMax(manualMaxRaw);
  }, [manualMinRaw, manualMaxRaw]);

  useEffect(() => {
    setMinInclusive(minInclusiveRaw !== "false");
    setMaxInclusive(maxInclusiveRaw !== "false");
  }, [minInclusiveRaw, maxInclusiveRaw]);

  useEffect(() => {
    const nextMin = parseRatingValue(sliderMinRaw ?? "") ?? RATING_SLIDER_MIN;
    const nextMax = parseRatingValue(sliderMaxRaw ?? "") ?? RATING_SLIDER_MAX;
    sliderValuesRef.current = { min: nextMin, max: nextMax };
    setSliderMin(nextMin);
    setSliderMax(nextMax);
  }, [sliderMinRaw, sliderMaxRaw]);

  function pushParams(params: URLSearchParams) {
    params.delete("page");
    const query = params.toString();
    const href = (query ? `${pathname}?${query}` : pathname) as Route;
    router.push(href, { scroll: false });
  }

  function commitManualRange(nextMin: string, nextMax: string) {
    let min = parseRatingValue(nextMin);
    let max = parseRatingValue(nextMax);
    if (min !== null && max !== null && min > max) {
      [min, max] = [max, min];
    }
    const params = new URLSearchParams(searchParams.toString());
    if (min === null) {
      params.delete("avg_rating_min");
    } else {
      params.set("avg_rating_min", formatRatingValue(min));
    }
    if (max === null) {
      params.delete("avg_rating_max");
    } else {
      params.set("avg_rating_max", formatRatingValue(max));
    }
    const nextMinInclusive = min === null ? true : minInclusive;
    const nextMaxInclusive = max === null ? true : maxInclusive;
    if (min === null || nextMinInclusive) {
      params.delete("avg_rating_min_inclusive");
    } else {
      params.set("avg_rating_min_inclusive", "false");
    }
    if (max === null || nextMaxInclusive) {
      params.delete("avg_rating_max_inclusive");
    } else {
      params.set("avg_rating_max_inclusive", "false");
    }
    setManualMin(min === null ? "" : formatRatingValue(min));
    setManualMax(max === null ? "" : formatRatingValue(max));
    setMinInclusive(nextMinInclusive);
    setMaxInclusive(nextMaxInclusive);
    sliderValuesRef.current = { min: min ?? RATING_SLIDER_MIN, max: max ?? RATING_SLIDER_MAX };
    setSliderMin(min ?? RATING_SLIDER_MIN);
    setSliderMax(max ?? RATING_SLIDER_MAX);
    pushParams(params);
  }

  function commitSliderRange(
    nextMin: number,
    nextMax: number,
    nextMinInclusive = minInclusive,
    nextMaxInclusive = maxInclusive,
  ) {
    const params = new URLSearchParams(searchParams.toString());
    if (nextMin <= RATING_SLIDER_MIN && nextMinInclusive) {
      params.delete("avg_rating_min");
    } else {
      params.set("avg_rating_min", formatRatingValue(nextMin));
    }
    if (nextMax >= RATING_SLIDER_MAX && nextMaxInclusive) {
      params.delete("avg_rating_max");
    } else {
      params.set("avg_rating_max", formatRatingValue(nextMax));
    }
    if (nextMin <= RATING_SLIDER_MIN && nextMinInclusive) {
      params.delete("avg_rating_min_inclusive");
    } else if (nextMinInclusive) {
      params.delete("avg_rating_min_inclusive");
    } else {
      params.set("avg_rating_min_inclusive", "false");
    }
    if (nextMax >= RATING_SLIDER_MAX && nextMaxInclusive) {
      params.delete("avg_rating_max_inclusive");
    } else if (nextMaxInclusive) {
      params.delete("avg_rating_max_inclusive");
    } else {
      params.set("avg_rating_max_inclusive", "false");
    }
    setManualMin(nextMin <= RATING_SLIDER_MIN && nextMinInclusive ? "" : formatRatingValue(nextMin));
    setManualMax(nextMax >= RATING_SLIDER_MAX && nextMaxInclusive ? "" : formatRatingValue(nextMax));
    setMinInclusive(nextMinInclusive);
    setMaxInclusive(nextMaxInclusive);
    sliderValuesRef.current = { min: nextMin, max: nextMax };
    setSliderMin(nextMin);
    setSliderMax(nextMax);
    pushParams(params);
  }

  function updateSliderPreview(nextMin: number, nextMax: number) {
    sliderValuesRef.current = { min: nextMin, max: nextMax };
    setSliderMin(nextMin);
    setSliderMax(nextMax);
    setManualMin(nextMin <= RATING_SLIDER_MIN && minInclusive ? "" : formatRatingValue(nextMin));
    setManualMax(nextMax >= RATING_SLIDER_MAX && maxInclusive ? "" : formatRatingValue(nextMax));
  }

  function snapSliderValue(value: number) {
    const snapped = Math.round(value / RATING_SLIDER_STEP) * RATING_SLIDER_STEP;
    return Math.max(RATING_SLIDER_MIN, Math.min(RATING_SLIDER_MAX, snapped));
  }

  function previewSliderFromPointer(handle: "min" | "max", clientX: number) {
    const track = document.getElementById("rating-range-track");
    if (!track) {
      return;
    }
    const bounds = track.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (clientX - bounds.left) / bounds.width));
    const nextValue = snapSliderValue(RATING_SLIDER_MIN + ratio * (RATING_SLIDER_MAX - RATING_SLIDER_MIN));
    const current = sliderValuesRef.current;
    if (handle === "min") {
      updateSliderPreview(Math.min(nextValue, current.max), current.max);
    } else {
      updateSliderPreview(current.min, Math.max(nextValue, current.min));
    }
  }

  function startSliderDrag(handle: "min" | "max", event: ReactPointerEvent<HTMLButtonElement>) {
    event.preventDefault();
    draggingHandleRef.current = handle;
    didDragRef.current = false;
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function moveSliderDrag(handle: "min" | "max", event: ReactPointerEvent<HTMLButtonElement>) {
    if (draggingHandleRef.current === handle) {
      didDragRef.current = true;
      previewSliderFromPointer(handle, event.clientX);
    }
  }

  function finishSliderDrag(handle: "min" | "max") {
    if (draggingHandleRef.current !== handle) {
      return;
    }
    draggingHandleRef.current = null;
    if (!didDragRef.current) {
      return;
    }
    const current = sliderValuesRef.current;
    commitSliderRange(current.min, current.max);
  }

  function cancelSliderDrag() {
    draggingHandleRef.current = null;
    didDragRef.current = false;
  }

  function toggleSliderInclusivity(handle: "min" | "max") {
    if (didDragRef.current) {
      didDragRef.current = false;
      return;
    }
    const nextMinInclusive = handle === "min" ? !minInclusive : minInclusive;
    const nextMaxInclusive = handle === "max" ? !maxInclusive : maxInclusive;
    commitSliderRange(sliderMin, sliderMax, nextMinInclusive, nextMaxInclusive);
  }

  function handleSliderKeyDown(handle: "min" | "max", event: ReactKeyboardEvent<HTMLButtonElement>) {
    const current = sliderValuesRef.current;
    const value = handle === "min" ? current.min : current.max;
    let nextValue: number | null = null;
    if (event.key === "ArrowLeft" || event.key === "ArrowDown") {
      nextValue = snapSliderValue(value) - RATING_SLIDER_STEP;
    } else if (event.key === "ArrowRight" || event.key === "ArrowUp") {
      nextValue = snapSliderValue(value) + RATING_SLIDER_STEP;
    } else if (event.key === "Home") {
      nextValue = RATING_SLIDER_MIN;
    } else if (event.key === "End") {
      nextValue = RATING_SLIDER_MAX;
    }
    if (nextValue === null) {
      return;
    }
    event.preventDefault();
    if (handle === "min") {
      commitSliderRange(Math.max(RATING_SLIDER_MIN, Math.min(nextValue, current.max)), current.max);
    } else {
      commitSliderRange(current.min, Math.min(RATING_SLIDER_MAX, Math.max(nextValue, current.min)));
    }
  }

  const sliderSpan = RATING_SLIDER_MAX - RATING_SLIDER_MIN;
  const selectedSliderStart = ((sliderMin - RATING_SLIDER_MIN) / sliderSpan) * 100;
  const selectedSliderWidth = ((sliderMax - sliderMin) / sliderSpan) * 100;

  return (
    <div className="flex flex-col gap-3 md:col-span-2">
      <span className="text-[0.6rem] font-semibold uppercase tracking-[0.2em] text-slate-400">
        Average Rating
      </span>
      <div className="flex flex-col gap-3">
        <div className="order-2 flex flex-wrap gap-3 text-xs text-slate-400">
          <label className="flex flex-col gap-1">
            <span>Manual min</span>
            <input
              type="text"
              inputMode="decimal"
              value={manualMin}
              placeholder="Any"
              onChange={(event) => setManualMin(event.target.value)}
              onBlur={() => commitManualRange(manualMin, manualMax)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  commitManualRange(manualMin, manualMax);
                }
              }}
              className="w-24 rounded border border-white/10 bg-black/40 px-3 py-2 text-sm text-white focus:border-brand-primary focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span>Manual max</span>
            <input
              type="text"
              inputMode="decimal"
              value={manualMax}
              placeholder="Any"
              onChange={(event) => setManualMax(event.target.value)}
              onBlur={() => commitManualRange(manualMin, manualMax)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  commitManualRange(manualMin, manualMax);
                }
              }}
              className="w-24 rounded border border-white/10 bg-black/40 px-3 py-2 text-sm text-white focus:border-brand-primary focus:outline-none"
            />
          </label>
          <p className="self-end pb-2 text-[0.65rem] text-slate-500">Inclusive; accepts 0–5.</p>
        </div>
        <div className="order-1 flex flex-col gap-2 text-xs text-slate-400">
          <div className="flex items-center justify-between">
            <span>Slider range</span>
            <span className="font-semibold text-white">
              {formatRatingValue(sliderMin)}–{formatRatingValue(sliderMax)}
            </span>
          </div>
          <div id="rating-range-track" className="relative h-7">
            <div className="absolute left-0 right-0 top-3 h-1 rounded-full bg-white/15" />
            <div
              className="absolute top-3 h-1 rounded-full bg-brand-primary"
              style={{ left: `${selectedSliderStart}%`, width: `${selectedSliderWidth}%` }}
            />
            <button
              aria-label={`Minimum slider rating (${minInclusive ? "inclusive" : "exclusive"})`}
              type="button"
              role="slider"
              aria-valuemin={RATING_SLIDER_MIN}
              aria-valuemax={RATING_SLIDER_MAX}
              aria-valuenow={sliderMin}
              tabIndex={0}
              onKeyDown={(event) => handleSliderKeyDown("min", event)}
              onPointerDown={(event) => startSliderDrag("min", event)}
              onPointerMove={(event) => moveSliderDrag("min", event)}
              onPointerUp={() => finishSliderDrag("min")}
              onPointerCancel={cancelSliderDrag}
              onClick={() => toggleSliderInclusivity("min")}
              title={minInclusive ? "Inclusive minimum; click to exclude" : "Exclusive minimum; click to include"}
              style={{ left: `${selectedSliderStart}%` }}
              className={`absolute top-1/2 z-30 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-brand-primary p-0 ${
                minInclusive ? "bg-brand-primary" : "bg-[color:var(--surface)]"
              }`}
            />
            <button
              aria-label={`Maximum slider rating (${maxInclusive ? "inclusive" : "exclusive"})`}
              type="button"
              role="slider"
              aria-valuemin={RATING_SLIDER_MIN}
              aria-valuemax={RATING_SLIDER_MAX}
              aria-valuenow={sliderMax}
              tabIndex={0}
              onKeyDown={(event) => handleSliderKeyDown("max", event)}
              onPointerDown={(event) => startSliderDrag("max", event)}
              onPointerMove={(event) => moveSliderDrag("max", event)}
              onPointerUp={() => finishSliderDrag("max")}
              onPointerCancel={cancelSliderDrag}
              onClick={() => toggleSliderInclusivity("max")}
              title={maxInclusive ? "Inclusive maximum; click to exclude" : "Exclusive maximum; click to include"}
              style={{ left: `${selectedSliderStart + selectedSliderWidth}%` }}
              className={`absolute top-1/2 z-30 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-brand-primary p-0 ${
                maxInclusive ? "bg-brand-primary" : "bg-[color:var(--surface)]"
              }`}
            />
          </div>
          <div className="flex justify-between text-[0.6rem] text-slate-500">
            <span>0.5</span>
            <span>5</span>
          </div>
        </div>
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
      const href = (nextQuery ? `${pathname}?${nextQuery}` : pathname) as Route;
      router.push(href, { scroll: false });
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
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:gap-4">
          <select
            className="w-full rounded border border-white/10 bg-black/40 px-3 py-2 text-sm text-white focus:border-brand-primary focus:outline-none sm:w-48"
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
          <DistributionSummary selectedValue={pendingValue ?? selectedValue} />
        </div>
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
    const href = (query ? `${pathname}?${query}` : pathname) as Route;
    router.push(href, { scroll: false });
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
      const href = (query ? `${pathname}?${query}` : pathname) as Route;
      router.push(href, { scroll: false });
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
    "avg_rating_min",
    "avg_rating_max",
    "avg_rating_min_inclusive",
    "avg_rating_max_inclusive",
    "watchers_min",
    "watchers_max",
    "letterboxd_source",
  ];
  const hasFilters = filterKeys.some((key) => searchParams.getAll(key).length > 0);
  const mapGenre = useCallback<MapResponseFn<GenreSearchResult>>(
    (item) => ({ value: String(item.id), label: item.name }),
    [],
  );
  const mapCountry = useCallback<MapResponseFn<CountrySearchResult>>(
    (item) => ({ value: item.code, label: item.name ?? item.code }),
    [],
  );
  const mapDirector = useCallback<MapResponseFn<DirectorSearchResult>>(
    (item) => ({ value: String(item.id), label: item.name }),
    [],
  );

  function clearFilters() {
    const params = new URLSearchParams(searchParams.toString());
    filterKeys.forEach((key) => params.delete(key));
    params.delete("page");
    const query = params.toString();
    const href = (query ? `${pathname}?${query}` : pathname) as Route;
    router.push(href, { scroll: false });
  }

  return (
    <div className="border-b border-white/10 px-6 py-4">
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-4 lg:flex-row">
          <MultiSelectFilter<GenreSearchResult>
            label="Genres"
            placeholder="Search genres"
            endpoint="/filters/genres"
            paramKey="genres"
            idParam="ids"
            mapResponse={mapGenre}
          />
          <MultiSelectFilter<CountrySearchResult>
            label="Countries"
            placeholder="Search countries"
            endpoint="/filters/countries"
            paramKey="countries"
            idParam="codes"
            mapResponse={mapCountry}
          />
          <MultiSelectFilter<DirectorSearchResult>
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
        <RatingRangeFilter />
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
