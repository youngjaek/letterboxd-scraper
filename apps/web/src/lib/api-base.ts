const publicApiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const serverApiBase = process.env.INTERNAL_API_BASE_URL ?? publicApiBase;

export function getApiBase(): string {
  if (typeof window === "undefined") {
    return serverApiBase;
  }
  return publicApiBase;
}

export { publicApiBase, serverApiBase };
