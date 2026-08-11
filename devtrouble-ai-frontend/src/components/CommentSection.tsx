import { useState, type FormEvent } from 'react';
import { Button } from './Button';
import { ErrorBanner, Spinner } from './Feedback';
import { Textarea } from './FormField';
import { useAddComment, useComments, useDeleteComment } from '../hooks/useComments';
import { useAuth } from '../store/AuthContext';
import { ApiError } from '../types/api';

export function CommentSection({ documentId }: { documentId: string }) {
  const { user } = useAuth();
  const { data: comments, isLoading } = useComments(documentId);
  const addComment = useAddComment(documentId);
  const deleteComment = useDeleteComment(documentId);

  const [content, setContent] = useState('');
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!content.trim()) return;
    setError(null);
    try {
      await addComment.mutateAsync({ content });
      setContent('');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '댓글 등록에 실패했습니다.');
    }
  }

  async function handleDelete(commentId: string) {
    if (!window.confirm('댓글을 삭제하시겠습니까?')) return;
    await deleteComment.mutateAsync(commentId);
  }

  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-sm font-semibold text-slate-500">
        댓글 {comments ? `(${comments.length})` : ''}
      </h2>

      <form onSubmit={(e) => void handleSubmit(e)} className="flex flex-col gap-2">
        {error && <ErrorBanner message={error} />}
        <Textarea
          rows={2}
          placeholder="댓글을 남겨보세요"
          value={content}
          onChange={(e) => setContent(e.target.value)}
        />
        <div className="flex justify-end">
          <Button type="submit" isLoading={addComment.isPending} disabled={!content.trim()}>
            댓글 등록
          </Button>
        </div>
      </form>

      {isLoading && (
        <div className="flex justify-center py-6">
          <Spinner />
        </div>
      )}

      {comments && comments.length === 0 && (
        <p className="text-sm text-slate-400">아직 댓글이 없습니다.</p>
      )}

      {comments && comments.length > 0 && (
        <ul className="flex flex-col gap-3">
          {comments.map((comment) => (
            <li key={comment.id} className="rounded-md border border-slate-200 bg-white p-3">
              <div className="flex items-start justify-between gap-3">
                <p className="whitespace-pre-wrap text-sm text-slate-800">{comment.content}</p>
                {user?.id === comment.author_id && (
                  <button
                    type="button"
                    onClick={() => void handleDelete(comment.id)}
                    className="shrink-0 text-xs text-slate-400 hover:text-red-600"
                  >
                    삭제
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
