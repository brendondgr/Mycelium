/** Partial-prefetch fallback while a project's detail route renders. */
export default function ProjectDetailLoading() {
  return (
    <div className="animate-pulse">
      {/* Back link, then the header's lab badge + project name. */}
      <div className="mb-[10px] h-7 w-28 rounded-full bg-surface-alt" />
      <div className="mb-[18px] flex items-center gap-3">
        <div className="h-6 w-32 rounded-full bg-surface-alt" />
        <div className="h-8 w-64 rounded-lg bg-surface-alt" />
      </div>
      {/* The page tab bar. */}
      <div className="mb-[22px] h-10 w-full max-w-[560px] rounded-lg bg-surface-alt" />
      {/* The About rail beside the workspace panel. */}
      <div className="grid grid-cols-1 gap-[22px] lg:grid-cols-5 lg:items-start">
        <div className="h-64 min-w-0 rounded-2xl bg-surface-alt lg:col-span-2" />
        <div className="h-64 min-w-0 rounded-2xl bg-surface-alt lg:col-span-3" />
      </div>
    </div>
  );
}
