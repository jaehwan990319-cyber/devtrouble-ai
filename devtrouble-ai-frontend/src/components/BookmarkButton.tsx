import { useMyBookmarkedIds, useToggleBookmark } from '../hooks/useBookmarks';

export function BookmarkButton({ documentId }: { documentId: string }) {
  const { data: bookmarkedIds } = useMyBookmarkedIds();
  const toggleBookmark = useToggleBookmark();

  const isBookmarked = bookmarkedIds?.includes(documentId) ?? false;

  return (
    <button
      type="button"
      onClick={() => toggleBookmark.mutate(documentId)}
      disabled={toggleBookmark.isPending}
      aria-pressed={isBookmarked}
      title={isBookmarked ? '즐겨찾기 해제' : '즐겨찾기 추가'}
      className={`inline-flex items-center gap-1.5 rounded-md border px-3 py-2 text-sm font-medium transition-colors
        ${
          isBookmarked
            ? 'border-amber-300 bg-amber-50 text-amber-700 hover:bg-amber-100'
            : 'border-slate-300 bg-white text-slate-600 hover:bg-slate-50'
        }`}
    >
      <span aria-hidden="true">{isBookmarked ? '★' : '☆'}</span>
      {isBookmarked ? '즐겨찾기됨' : '즐겨찾기'}
    </button>
  );
}
