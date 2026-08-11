import { useEffect } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { BookmarkButton } from '../components/BookmarkButton';
import { Button } from '../components/Button';
import { CommentSection } from '../components/CommentSection';
import { ErrorBanner, Spinner } from '../components/Feedback';
import { MarkdownPreview } from '../components/MarkdownPreview';
import { TagBadge } from '../components/TagBadge';
import { useRecordRecentView } from '../hooks/useBookmarks';
import { useDeleteDocument, useDocument } from '../hooks/useDocuments';
import { useAuth } from '../store/AuthContext';

function Section({ title, content }: { title: string; content: string | null }) {
  if (!content) return null;
  return (
    <section>
      <h2 className="mb-2 text-sm font-semibold text-slate-500">{title}</h2>
      <MarkdownPreview content={content} />
    </section>
  );
}

export function DocumentDetailPage() {
  const { documentId } = useParams<{ documentId: string }>();
  const { user } = useAuth();
  const navigate = useNavigate();
  const { data: document, isLoading, isError } = useDocument(documentId);
  const deleteDocument = useDeleteDocument();
  const recordRecentView = useRecordRecentView();

  useEffect(() => {
    // 로그인 사용자가 문서 상세에 진입하면 "최근 본 문서"에 기록한다.
    // 실패해도 화면에는 영향이 없어야 하므로 별도 에러 처리를 하지 않는다.
    if (user && documentId) {
      recordRecentView.mutate(documentId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, documentId]);

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <Spinner />
      </div>
    );
  }

  if (isError || !document) {
    return <ErrorBanner message="문서를 찾을 수 없습니다." />;
  }

  const isAuthor = user?.id === document.author_id;

  async function handleDelete() {
    if (!documentId) return;
    if (!window.confirm('정말 삭제하시겠습니까?')) return;
    await deleteDocument.mutateAsync(documentId);
    navigate('/documents');
  }

  return (
    <article className="flex flex-col gap-6">
      <div>
        <Link to="/documents" className="text-sm text-slate-500 hover:text-brand-600">
          ← 목록으로
        </Link>

        <div className="mt-2 flex items-start justify-between gap-4">
          <h1 className="text-2xl font-bold text-slate-900">{document.title}</h1>
          <div className="flex shrink-0 gap-2">
            {user && <BookmarkButton documentId={document.id} />}
            {isAuthor && (
              <>
                <Link to={`/documents/${document.id}/edit`}>
                  <Button variant="secondary">수정</Button>
                </Link>
                <Button variant="danger" onClick={() => void handleDelete()} isLoading={deleteDocument.isPending}>
                  삭제
                </Button>
              </>
            )}
          </div>
        </div>

        {document.tag_names.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {document.tag_names.map((tag) => (
              <TagBadge key={tag} label={tag} />
            ))}
          </div>
        )}

        <p className="mt-3 text-xs text-slate-400">
          조회 {document.view_count} · {new Date(document.created_at).toLocaleString('ko-KR')}
        </p>
      </div>

      <Section title="문제 설명" content={document.problem_description} />
      <Section title="에러 메시지" content={document.error_message} />
      <Section title="Stack Trace" content={document.stack_trace} />
      <Section title="해결 방법" content={document.solution} />
      <Section title="회고" content={document.retrospective} />

      <div className="border-t border-slate-200 pt-6">
        <CommentSection documentId={document.id} />
      </div>
    </article>
  );
}
