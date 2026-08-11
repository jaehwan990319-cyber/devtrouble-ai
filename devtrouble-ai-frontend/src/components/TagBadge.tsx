export function TagBadge({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center rounded-full bg-brand-50 px-2.5 py-0.5 text-xs font-medium text-brand-700">
      #{label}
    </span>
  );
}
