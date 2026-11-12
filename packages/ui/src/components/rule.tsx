/**
 * A hairline rule with an optional centred label, such as "or" between sign-in methods. The label
 * stays readable to screen readers; the lines are decoration.
 */
export function Rule({ label }: { label?: string }) {
  if (!label) return <hr className="border-umber" />;
  return (
    <div className="flex items-center gap-3">
      <span aria-hidden="true" className="h-px flex-1 bg-umber" />
      <span className="font-display text-parchment italic">{label}</span>
      <span aria-hidden="true" className="h-px flex-1 bg-umber" />
    </div>
  );
}
