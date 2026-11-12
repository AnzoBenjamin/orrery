/** A hairline rule in the surface's ink, optionally with a centred italic word such as "or". */
export function Rule({ label }: { label?: string }) {
  if (!label) return <hr className="border-[var(--rule)]" />;
  return (
    <div className="flex items-center gap-4 text-[var(--ink)]">
      <span aria-hidden="true" className="h-px flex-1 bg-[var(--rule)]" />
      <span className="font-display text-lg italic">{label}</span>
      <span aria-hidden="true" className="h-px flex-1 bg-[var(--rule)]" />
    </div>
  );
}
