import { isDemoMode } from "@/lib/demo-flags";

type DemoBannerProps = {
  className?: string;
};

export function DemoBanner({ className }: DemoBannerProps) {
  if (!isDemoMode) {
    return null;
  }
  const classes = [
    "rounded-xl border border-yellow-400/40 bg-yellow-500/10 px-4 py-3 text-sm text-yellow-200",
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={classes}>
      Kinoboxd is running in <span className="font-semibold text-yellow-100">demo mode</span>. The rankings and
      filters showcase Alexy&apos;s private cohort data, and write actions (create/sync/delete) are disabled while we
      pursue official Letterboxd API access.
    </div>
  );
}
