const features = [
  "Living lab profiles",
  "Research and evidence tracking",
  "Grant and fellowship matching",
];

export default function Home() {
  return (
    <main className="min-h-screen bg-[var(--background)] text-[var(--foreground)]">
      <section className="mx-auto flex min-h-screen w-full max-w-6xl flex-col justify-center gap-12 px-6 py-16 sm:px-10 lg:px-12">
        <div className="max-w-3xl">
          <p className="mb-4 text-sm font-medium uppercase tracking-wide text-[var(--brand-primary)]">
            Mycelium
          </p>
          <h1 className="text-4xl font-semibold leading-tight text-[var(--text-primary)] sm:text-6xl">
            Living intelligence for research labs.
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-[var(--text-secondary)]">
            Mycelium helps labs connect papers, people, projects, grants,
            fellowships, and evidence-backed reports into one research memory.
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          {features.map((feature) => (
            <div
              key={feature}
              className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5 shadow-sm"
            >
              <p className="text-base font-medium text-[var(--text-primary)]">
                {feature}
              </p>
            </div>
          ))}
        </div>

        <div className="flex flex-wrap gap-3">
          <a
            className="inline-flex min-h-11 items-center rounded-md bg-[var(--brand-primary)] px-5 text-sm font-medium text-white transition hover:bg-[var(--brand-primary-hover)]"
            href="/app"
          >
            Open workspace
          </a>
          <a
            className="inline-flex min-h-11 items-center rounded-md border border-[var(--border)] bg-[var(--surface)] px-5 text-sm font-medium text-[var(--text-primary)] transition hover:bg-[var(--surface-alt)]"
            href={`${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api"}/health/`}
          >
            API health
          </a>
        </div>
      </section>
    </main>
  );
}
