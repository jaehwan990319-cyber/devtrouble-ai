export function Spinner({ className = '' }: { className?: string }) {
  return (
    <div
      role="status"
      aria-label="로딩 중"
      className={`h-6 w-6 animate-spin rounded-full border-2 border-slate-300 border-t-brand-500 ${className}`}
    />
  );
}

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{message}</div>
  );
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-md border border-dashed border-slate-300 px-6 py-12 text-sm text-slate-500">
      {message}
    </div>
  );
}
