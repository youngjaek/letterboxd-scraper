export const RESULT_LIMIT_OPTIONS = [100, 250, 500, 1000] as const;
export type ResultLimitOption = (typeof RESULT_LIMIT_OPTIONS)[number];
export const DEFAULT_RESULT_LIMIT: ResultLimitOption = 250;

export const PAGE_SIZE_OPTIONS = [25, 50, 100] as const;
export type PageSizeOption = (typeof PAGE_SIZE_OPTIONS)[number];
export const DEFAULT_PAGE_SIZE: PageSizeOption = 50;

function coerceOption(
  value: string | string[] | undefined,
  options: readonly number[],
  defaultValue: number,
): number {
  const raw = Array.isArray(value) ? value[0] : value;
  if (!raw) {
    return defaultValue;
  }
  const parsed = parseInt(raw, 10);
  if (Number.isNaN(parsed)) {
    return defaultValue;
  }
  return options.includes(parsed) ? parsed : defaultValue;
}

export function parseResultLimit(value: string | string[] | undefined): ResultLimitOption {
  return coerceOption(value, RESULT_LIMIT_OPTIONS, DEFAULT_RESULT_LIMIT) as ResultLimitOption;
}

export function parsePageSize(value: string | string[] | undefined): PageSizeOption {
  return coerceOption(value, PAGE_SIZE_OPTIONS, DEFAULT_PAGE_SIZE) as PageSizeOption;
}
