function normalize(value: string | undefined): string {
  return value?.trim() ?? "";
}

function isLoopbackHost(value: string): boolean {
  try {
    const parsed = new URL(value);
    return ["127.0.0.1", "0.0.0.0", "localhost"].includes(parsed.hostname);
  } catch {
    return false;
  }
}

const configuredPublicBase = normalize(process.env.NEXT_PUBLIC_API_BASE_URL);
const internalBase = normalize(process.env.INTERNAL_API_BASE_URL);

const serverApiBase = internalBase || configuredPublicBase || "http://localhost:8000";

function resolveBrowserBase(): string {
  if (configuredPublicBase && !isLoopbackHost(configuredPublicBase)) {
    return configuredPublicBase;
  }
  if (typeof window !== "undefined") {
    return `${window.location.origin}/api/backend`;
  }
  return "/api/backend";
}

export function getApiBase(): string {
  if (typeof window === "undefined") {
    return serverApiBase;
  }
  return resolveBrowserBase();
}

const publicApiBase = configuredPublicBase || "/api/backend";

export { publicApiBase, serverApiBase };
