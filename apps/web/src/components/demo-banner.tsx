import { isDemoMode } from "@/lib/demo-flags";

type DemoBannerProps = {
  className?: string;
};

export function DemoBanner({ className }: DemoBannerProps) {
  if (!isDemoMode) {
    return null;
  }
  const classes = [
    "panel-soft flex flex-wrap items-center justify-between gap-3 text-sm",
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={classes}>
      <div className="flex items-center gap-3">
        <span className="status-chip">Preview mode</span>
        <p className="muted-copy">
          This public build is read-only. You can browse cohorts and rankings, while creation and sync controls stay
          disabled.
        </p>
      </div>
    </div>
  );
}
