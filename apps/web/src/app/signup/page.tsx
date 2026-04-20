import Link from "next/link";

export default function SignupPage() {
  return (
    <section className="mx-auto flex w-full max-w-2xl flex-col items-center gap-5 pb-12 pt-8 text-center">
      <div className="panel w-full space-y-3">
        <p className="eyebrow">Coming soon</p>
        <h1 className="section-title">Sign up is not available yet.</h1>
        <p className="text-sm leading-7 text-[color:var(--text-soft)]">
          Account features are planned. For now, you can search and browse public canons.
        </p>
        <div className="flex flex-wrap justify-center gap-3 pt-2">
          <Link href="/cohorts" className="button-primary">
            Browse canons
          </Link>
          <Link href="/" className="button-secondary">
            Back home
          </Link>
        </div>
      </div>
    </section>
  );
}
