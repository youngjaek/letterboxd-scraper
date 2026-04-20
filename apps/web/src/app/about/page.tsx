export default function AboutPage() {
  return (
    <section className="mx-auto flex w-full max-w-4xl flex-col gap-6 pb-12">
      <header className="panel space-y-3">
        <p className="eyebrow">About</p>
        <h1 className="section-title">What Kinoboxd is</h1>
        <p className="text-sm leading-7 text-[color:var(--text-soft)] sm:text-base">
          Kinoboxd helps Letterboxd users browse a user&apos;s friends&apos; canon of films. Instead of looking at one
          person&apos;s diary, you can explore the shared favorites of their circle.
        </p>
      </header>

      <section className="panel-soft space-y-3">
        <h2 className="text-xl font-semibold text-[color:var(--text)]">What you can do</h2>
        <p className="text-sm leading-7 text-[color:var(--text-soft)]">
          Search for an existing canon, browse the ranking board, and inspect what a user&apos;s followings seem to love
          most. Logged-in users will eventually be able to request new canon builds.
        </p>
      </section>

      <section className="panel-soft space-y-3">
        <h2 className="text-xl font-semibold text-[color:var(--text)]">Data sources</h2>
        <p className="text-sm leading-7 text-[color:var(--text-soft)]">
          Kinoboxd uses public Letterboxd profile and rating data together with TMDB metadata. Kinoboxd is not
          affiliated with Letterboxd or TMDB.
        </p>
        <p className="text-sm leading-7 text-[color:var(--text-soft)]">
          Use of those services is subject to their own terms.
        </p>
      </section>
    </section>
  );
}
