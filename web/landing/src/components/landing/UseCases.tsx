import { useCases } from "@/data/landing";

export function UseCases() {
  return (
    <section className="border-b border-border py-14 sm:py-16" aria-labelledby="use-cases-heading">
      <div className="mx-auto w-full max-w-6xl px-4 sm:px-6 lg:px-8">
        <div className="max-w-2xl">
          <h2
            id="use-cases-heading"
            className="font-display text-2xl font-semibold text-[var(--text-primary)] sm:text-3xl"
          >
            Built for every role in the lab
          </h2>
          <p className="mt-3 text-base leading-7 text-[var(--text-secondary)]">
            Mycelium adapts to how PIs, trainees, grant writers, and administrators
            actually work—without turning research into a toy chatbot.
          </p>
        </div>

        <div className="mt-10 grid gap-4 sm:grid-cols-2">
          {useCases.map(({ title, description, icon: Icon }) => (
            <article
              key={title}
              className="rounded-lg border border-border bg-card p-5 shadow-sm"
            >
              <span className="inline-flex size-10 items-center justify-center rounded-full bg-primary/15 text-primary">
                <Icon aria-hidden className="size-5" />
              </span>
              <h3 className="mt-4 text-lg font-semibold text-[var(--text-primary)]">{title}</h3>
              <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
                {description}
              </p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
