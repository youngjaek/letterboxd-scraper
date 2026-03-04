type CacheEntry<T> = {
  expiresAt: number;
  value: Promise<T>;
};

const cacheStore = new Map<string, CacheEntry<unknown>>();

function getCacheKey(key: string): string {
  return key;
}

export function cacheResult<T>(key: string, ttlMs: number, fetcher: () => Promise<T>): Promise<T> {
  const now = Date.now();
  const cacheKey = getCacheKey(key);
  const existing = cacheStore.get(cacheKey);
  if (existing && existing.expiresAt > now) {
    return existing.value as Promise<T>;
  }
  const promise = fetcher();
  cacheStore.set(cacheKey, { value: promise, expiresAt: now + ttlMs });
  promise.catch(() => {
    cacheStore.delete(cacheKey);
  });
  return promise;
}

export function clearCache(keyPrefix?: string): void {
  if (!keyPrefix) {
    cacheStore.clear();
    return;
  }
  const normalized = keyPrefix.trim();
  for (const key of cacheStore.keys()) {
    if (key.startsWith(normalized)) {
      cacheStore.delete(key);
    }
  }
}
