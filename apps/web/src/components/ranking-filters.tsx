"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

type Option = {
  value: string;
  label: string;
  hint?: string | null;
};

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

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
    router.push(queryString ? `${pathname}?${queryString}` : pathname);
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

function YearInput({ label, paramKey }: { label: string; paramKey: string }) {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const rawValue = searchParams?.get(paramKey) ?? "";
  const [value, setValue] = useState(rawValue);

  useEffect(() => {
    setValue(rawValue);
  }, [rawValue]);

  function commit(next: string) {
    const params = new URLSearchParams(searchParams?.toString() ?? "");
    const trimmed = next.trim();
    if (trimmed) {
      params.set(paramKey, trimmed);
    } else {
      params.delete(paramKey);
    }
    params.delete("page");
    const query = params.toString();
    router.push(query ? `${pathname}?${query}` : pathname);
  }

  return (
    <label className="flex flex-col text-xs uppercase tracking-[0.2em] text-slate-400">
      {label}
      <input
        type="number"
        min={1900}
        max={2100}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onBlur={() => commit(value)}
        className="mt-1 rounded border border-white/10 bg-black/40 px-2 py-2 text-sm text-white focus:border-brand-primary focus:outline-none"
      />
    </label>
  );
}

function DecadeSelect() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const value = searchParams?.get("decade") ?? "";
  const decades = Array.from({ length: 12 }).map((_, index) => 1950 + index * 10);

  function update(next: string) {
    const params = new URLSearchParams(searchParams?.toString() ?? "");
    if (next) {
      params.set("decade", next);
    } else {
      params.delete("decade");
    }
    params.delete("page");
    const query = params.toString();
    router.push(query ? `${pathname}?${query}` : pathname);
  }

  return (
    <label className="flex flex-col text-xs uppercase tracking-[0.2em] text-slate-400">
      Decade
      <select
        value={value}
        onChange={(event) => update(event.target.value)}
        className="mt-1 rounded border border-white/10 bg-black/40 px-2 py-2 text-sm text-white focus:border-brand-primary focus:outline-none"
      >
        <option value="">Any</option>
        {decades.map((decade) => (
          <option key={decade} value={decade}>
            {decade}s
          </option>
        ))}
      </select>
    </label>
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
    router.push(query ? `${pathname}?${query}` : pathname);
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
        <div className="flex flex-wrap gap-4">
          <YearInput label="Year from" paramKey="release_year_min" />
          <YearInput label="Year to" paramKey="release_year_max" />
          <DecadeSelect />
          <button
            type="button"
            onClick={clearFilters}
            disabled={!hasFilters}
            className="self-end rounded border border-white/20 px-3 py-2 text-xs uppercase tracking-[0.2em] text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            Clear filters
          </button>
        </div>
      </div>
    </div>
  );
}
