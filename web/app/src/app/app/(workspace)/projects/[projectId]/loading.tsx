/** Partial-prefetch fallback while a project's detail route renders. */
export default function ProjectDetailLoading() {
  return (
    <div className="animate-pulse">
      <div className="mb-[14px] h-7 w-28 rounded-full bg-surface-alt" />
      <div className="mb-[22px] h-9 w-64 rounded-lg bg-surface-alt" />
      <div className="grid items-start gap-[22px] lg:grid-cols-[1.55fr_1fr]">
        <div className="h-64 rounded-2xl bg-surface-alt" />
        <div className="h-64 rounded-2xl bg-surface-alt" />
      </div>
    </div>
  );
}
