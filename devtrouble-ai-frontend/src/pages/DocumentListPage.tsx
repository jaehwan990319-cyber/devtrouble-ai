import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Input } from '../components/FormField';
import { Button } from '../components/Button';
import { Spinner, ErrorBanner, EmptyState } from '../components/Feedback';
import { TagBadge } from '../components/TagBadge';
import { useDocumentSearch } from '../hooks/useDocuments';
import type { DocumentSearchParams } from '../types/document';

export function DocumentListPage() {
  const [searchParams] = useSearchParams();
  const initialProjectId = searchParams.get('project_id') ?? undefined;

  const [formState, setFormState] = useState<DocumentSearchParams>({ project_id: initialProjectId });
  const [appliedParams, setAppliedParams] = useState<DocumentSearchParams>({ project_id: initialProjectId });

  const { data: documents, isLoading, isError } = useDocumentSearch(appliedParams);

  function handleSearch() {
    setAppliedParams(formState);
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">트러블슈팅 문서</h1>
        <p className="mt-1 text-sm text-slate-500">키워드, 태그, 에러 코드로 과거 트러블슈팅 기록을 검색하세요.</p>
      </div>

      <div className="grid grid-cols-1 gap-3 rounded-lg border border-slate-200 bg-white p-4 sm:grid-cols-4">
        <Input
          placeholder="키워드 (제목/본문/에러메시지)"
          value={formState.keyword ?? ''}
          onChange={(e) => setFormState((prev) => ({ ...prev, keyword: e.target.value || undefined }))}
        />
        <Input
          placeholder="태그"
          value={formState.tag ?? ''}
          onChange={(e) => setFormState((prev) => ({ ...prev, tag: e.target.value || undefined }))}
        />
        <Input
          placeholder="에러 코드"
          value={formState.error_code ?? ''}
          onChange={(e) => setFormState((prev) => ({ ...prev, error_code: e.target.value || undefined }))}
        />
        <Button onClick={handleSearch}>검색</Button>
      </div>

      {isLoading && (
        <div className="flex justify-center py-12">
          <Spinner />
        </div>
      )}

      {isError && <ErrorBanner message="문서 목록을 불러오지 못했습니다." />}

      {documents && documents.length === 0 && <EmptyState message="검색 결과가 없습니다." />}

      {documents && documents.length > 0 && (
        <ul className="flex flex-col gap-3">
          {documents.map((doc) => (
            <li key={doc.id}>
              <Link
                to={`/documents/${doc.id}`}
                className="block rounded-lg border border-slate-200 bg-white p-4 transition-shadow hover:shadow-md"
              >
                <div className="flex items-start justify-between gap-4">
                  <h2 className="font-semibold text-slate-900">{doc.title}</h2>
                  <span className="shrink-0 text-xs text-slate-400">조회 {doc.view_count}</span>
                </div>
                {doc.tag_names.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {doc.tag_names.map((tag) => (
                      <TagBadge key={tag} label={tag} />
                    ))}
                  </div>
                )}
                <p className="mt-2 text-xs text-slate-400">
                  {new Date(doc.created_at).toLocaleDateString('ko-KR')}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
