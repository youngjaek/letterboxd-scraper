"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

type SearchParamsContextValue = {
  params: URLSearchParams;
  updateParams: (mutate: (params: URLSearchParams) => void, options?: { updateHistory?: boolean }) => void;
};

const SearchParamsContext = createContext<SearchParamsContextValue | null>(null);

export function SearchParamsProvider({
  initialQueryString,
  children,
}: {
  initialQueryString: string;
  children: ReactNode;
}) {
  const [queryString, setQueryString] = useState(initialQueryString);

  useEffect(() => {
    setQueryString(initialQueryString);
  }, [initialQueryString]);

  const updateParams = useCallback((mutate: (params: URLSearchParams) => void, options?: { updateHistory?: boolean }) => {
    setQueryString((prev) => {
      const next = new URLSearchParams(prev);
      mutate(next);
      const nextString = next.toString();
      if (options?.updateHistory !== false && typeof window !== "undefined") {
        const basePath = window.location.pathname;
        const nextUrl = nextString ? `${basePath}?${nextString}` : basePath;
        window.history.replaceState(null, "", nextUrl);
      }
      return nextString;
    });
  }, []);

  const params = useMemo(() => new URLSearchParams(queryString), [queryString]);

  const value = useMemo<SearchParamsContextValue>(
    () => ({
      params,
      updateParams,
    }),
    [params, updateParams],
  );

  return <SearchParamsContext.Provider value={value}>{children}</SearchParamsContext.Provider>;
}

export function useSyncedSearchParams(): URLSearchParams {
  const context = useContext(SearchParamsContext);
  if (!context) {
    throw new Error("useSyncedSearchParams must be used within SearchParamsProvider");
  }
  return context.params;
}

export function useSearchParamsUpdater() {
  const context = useContext(SearchParamsContext);
  if (!context) {
    throw new Error("useSearchParamsUpdater must be used within SearchParamsProvider");
  }
  return context.updateParams;
}
