const demoFlag =
  process.env.NEXT_PUBLIC_DEMO_MODE ??
  process.env.DEMO_MODE ??
  "";

function normalizeBoolean(value: string | undefined | null): boolean {
  if (!value) {
    return false;
  }
  const normalized = value.toString().trim().toLowerCase();
  return ["1", "true", "yes", "on"].includes(normalized);
}

export const isDemoMode = normalizeBoolean(demoFlag);
