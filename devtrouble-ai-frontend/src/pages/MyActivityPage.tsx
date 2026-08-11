import { Link } from 'react-router-dom';
import { EmptyState, Spinner } from '../components/Feedback';
import { useMyBookmarkedIds, useRecentViewIds } from '../hooks/useBookmarks';

function DocumentIdList({
  ids,
  isLoading,
  emptyMessage,
}: {
  ids: string[] | undefined;
  isLoading: boolean;
  emptyMessage: string;
}) {
  if (isLoading) {
    return (
      <div className="flex justify-center py-6">
        <Spinner />
      </div>
    );
  }

  if (!ids || ids.length === 0) {
    return <EmptyState message={emptyMessage} />;
  }

  return (
    <ul className="flex flex-col gap-2">
      {ids.map((documentId) => (
        <li key={documentId}>
          <Link
            to={`/documents/${documentId}`}
            className="block rounded-md border border-slate-200 bg-white px-4 py-3 text-sm text-brand-600 hover:bg-slate-50 hover:underline"
          >
            {documentId}
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function MyActivityPage() {
  const { data: bookmarkedIds, isLoading: isLoadingBookmarks } = useMyBookmarkedIds();
  const { data: recentViewIds, isLoading: isLoadingRecentViews } = useRecentViewIds();

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">내 활동</h1>
        <p className="mt-1 text-sm text-slate-500">즐겨찾기한 문서와 최근에 본 문서를 확인하세요.</p>
      </div>

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold text-slate-500">★ 즐겨찾기</h2>
        <DocumentIdList
          ids={bookmarkedIds}
          isLoading={isLoadingBookmarks}
          emptyMessage="즐겨찾기한 문서가 없습니다."
        />
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold text-slate-500">최근 본 문서</h2>
        <DocumentIdList
          ids={recentViewIds}
          isLoading={isLoadingRecentViews}
          emptyMessage="최근 본 문서가 없습니다."
        />
      </section>
    </div>
  );
}
