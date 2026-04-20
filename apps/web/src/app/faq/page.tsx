const questions = [
  {
    question: "Do I need a Letterboxd account to browse Kinoboxd?",
    answer: "No. Anyone can browse existing canons.",
  },
  {
    question: "Who can create a ranking?",
    answer: "If you log in, you can create a ranking for one user's friends.",
  },
  {
    question: "What does build a canon mean?",
    answer:
      "It starts from one seed user and builds a ranking board from that user's followings' ratings.",
  },
  {
    question: "Can I search by username?",
    answer: "Yes. Search a Letterboxd username from the search page.",
  },
  {
    question: "Is Kinoboxd affiliated with Letterboxd or TMDB?",
    answer: "No. Kinoboxd is an independent project that uses public data and metadata.",
  },
];

export default function FaqPage() {
  return (
    <section className="mx-auto flex w-full max-w-4xl flex-col gap-6 pb-12">
      <header className="panel space-y-3">
        <p className="eyebrow">Frequently Asked Questions</p>
        <h1 className="section-title">Frequently Asked Questions</h1>
      </header>

      <div className="space-y-4">
        {questions.map((item) => (
          <article key={item.question} className="panel-soft space-y-2">
            <h2 className="text-lg font-semibold text-[color:var(--text)]">{item.question}</h2>
            <p className="text-sm leading-7 text-[color:var(--text-soft)]">{item.answer}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
