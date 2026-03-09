import { DemoBanner } from "@/components/demo-banner";

function SkeletonLine({ className = "" }: { className?: string }) {
  return <div className={`rounded-full bg-white/10 ${className}`} />;
}

function SkeletonBlock({ className = "" }: { className?: string }) {
  return <div className={`rounded-md bg-white/10 ${className}`} />;
}

export default function CohortLoading() {
  const rankingPlaceholders = Array.from({ length: 5 });
  return (
    <section className="mx-auto flex max-w-4xl flex-col gap-6">
      <DemoBanner />
      <div className="rounded-xl border border-white/10 bg-white/5 p-6">
        <div className="space-y-3 animate-pulse">
          <SkeletonLine className="h-3 w-24 bg-brand-accent/40" />
          <SkeletonLine className="h-8 w-2/3" />
          <SkeletonLine className="h-4 w-40" />
          <SkeletonLine className="h-4 w-52" />
          <SkeletonLine className="h-4 w-48" />
          <SkeletonLine className="h-4 w-24" />
        </div>
      </div>
      <div className="rounded-xl border border-white/10 bg-white/5 px-6 py-5">
        <div className="space-y-4 animate-pulse">
          <SkeletonLine className="h-4 w-32" />
          <SkeletonBlock className="h-16" />
        </div>
      </div>
      <div className="rounded-xl border border-white/10 bg-white/5">
        <div className="flex items-center justify-between border-b border-white/10 px-6 py-4">
          <SkeletonLine className="h-4 w-28" />
          <SkeletonLine className="h-4 w-40" />
        </div>
        <div className="border-b border-white/10 px-6 py-4">
          <SkeletonLine className="h-4 w-24" />
        </div>
        <div className="space-y-4 px-6 py-6">
          <div className="flex items-center justify-between">
            <SkeletonLine className="h-3 w-32" />
            <SkeletonLine className="h-3 w-20" />
          </div>
          <div className="space-y-4">
            {rankingPlaceholders.map((_, index) => (
              <div key={index} className="flex items-center justify-between border-b border-white/5 pb-3 last:border-none last:pb-0">
                <SkeletonLine className="h-4 w-48" />
                <div className="flex flex-col items-end gap-2">
                  <SkeletonLine className="h-3 w-20" />
                  <SkeletonLine className="h-3 w-16" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
