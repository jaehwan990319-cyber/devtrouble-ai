import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Button } from '../components/Button';
import { ErrorBanner, Spinner } from '../components/Feedback';
import { Input, Select, Textarea } from '../components/FormField';
import { useCreateDocument, useDocument, useUpdateDocument } from '../hooks/useDocuments';
import { useMyProjects } from '../hooks/useProjects';
import { ApiError } from '../types/api';

interface FormState {
  projectId: string;
  title: string;
  problemDescription: string;
  errorMessage: string;
  stackTrace: string;
  solution: string;
  retrospective: string;
  tagsText: string;
}

const EMPTY_FORM: FormState = {
  projectId: '',
  title: '',
  problemDescription: '',
  errorMessage: '',
  stackTrace: '',
  solution: '',
  retrospective: '',
  tagsText: '',
};

export function DocumentFormPage() {
  const { documentId } = useParams<{ documentId: string }>();
  const isEditMode = Boolean(documentId);
  const navigate = useNavigate();

  const { data: existingDocument, isLoading: isLoadingDocument } = useDocument(documentId);
  const { data: projects, isLoading: isLoadingProjects } = useMyProjects();
  const createDocument = useCreateDocument();
  const updateDocument = useUpdateDocument(documentId ?? '');

  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (existingDocument) {
      setForm({
        projectId: existingDocument.project_id,
        title: existingDocument.title,
        problemDescription: existingDocument.problem_description,
        errorMessage: existingDocument.error_message ?? '',
        stackTrace: existingDocument.stack_trace ?? '',
        solution: existingDocument.solution ?? '',
        retrospective: existingDocument.retrospective ?? '',
        tagsText: existingDocument.tag_names.join(', '),
      });
    }
  }, [existingDocument]);

  function updateField<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    const tagNames = form.tagsText
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);

    try {
      if (isEditMode && documentId) {
        const updated = await updateDocument.mutateAsync({
          title: form.title,
          problem_description: form.problemDescription,
          error_message: form.errorMessage || undefined,
          stack_trace: form.stackTrace || undefined,
          solution: form.solution || undefined,
          retrospective: form.retrospective || undefined,
          tag_names: tagNames,
        });
        navigate(`/documents/${updated.id}`);
      } else {
        const created = await createDocument.mutateAsync({
          project_id: form.projectId,
          title: form.title,
          problem_description: form.problemDescription,
          error_message: form.errorMessage || undefined,
          stack_trace: form.stackTrace || undefined,
          solution: form.solution || undefined,
          retrospective: form.retrospective || undefined,
          tag_names: tagNames,
        });
        navigate(`/documents/${created.id}`);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '저장에 실패했습니다.');
    }
  }

  if (isEditMode && isLoadingDocument) {
    return (
      <div className="flex justify-center py-12">
        <Spinner />
      </div>
    );
  }

  const isSubmitting = createDocument.isPending || updateDocument.isPending;

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="mb-6 text-2xl font-bold text-slate-900">
        {isEditMode ? '트러블슈팅 문서 수정' : '새 트러블슈팅 문서 작성'}
      </h1>

      <form onSubmit={(e) => void handleSubmit(e)} className="flex flex-col gap-4">
        {error && <ErrorBanner message={error} />}

        {!isEditMode && (
          <>
            {projects && projects.length === 0 ? (
              <ErrorBanner message="문서를 작성하려면 먼저 프로젝트가 있어야 합니다." />
            ) : (
              <Select
                label="프로젝트"
                required
                placeholder={isLoadingProjects ? '불러오는 중...' : '프로젝트를 선택하세요'}
                options={(projects ?? []).map((p) => ({ value: p.id, label: p.name }))}
                value={form.projectId}
                onChange={(e) => updateField('projectId', e.target.value)}
              />
            )}
            {projects && projects.length === 0 && (
              <Link to="/projects" className="text-sm text-brand-600 hover:underline">
                프로젝트 만들러 가기 →
              </Link>
            )}
          </>
        )}

        <Input
          label="제목"
          required
          value={form.title}
          onChange={(e) => updateField('title', e.target.value)}
        />
        <Textarea
          label="문제 설명 (Markdown 지원)"
          required
          rows={4}
          value={form.problemDescription}
          onChange={(e) => updateField('problemDescription', e.target.value)}
        />
        <Textarea
          label="에러 메시지"
          rows={2}
          value={form.errorMessage}
          onChange={(e) => updateField('errorMessage', e.target.value)}
        />
        <Textarea
          label="Stack Trace"
          rows={4}
          value={form.stackTrace}
          onChange={(e) => updateField('stackTrace', e.target.value)}
        />
        <Textarea
          label="해결 방법 (Markdown 지원)"
          rows={4}
          value={form.solution}
          onChange={(e) => updateField('solution', e.target.value)}
        />
        <Textarea
          label="회고 (Markdown 지원)"
          rows={3}
          value={form.retrospective}
          onChange={(e) => updateField('retrospective', e.target.value)}
        />
        <Input
          label="태그 (쉼표로 구분)"
          placeholder="예: sqlalchemy, mysql, deadlock"
          value={form.tagsText}
          onChange={(e) => updateField('tagsText', e.target.value)}
        />

        <div className="mt-2 flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={() => navigate(-1)}>
            취소
          </Button>
          <Button type="submit" isLoading={isSubmitting}>
            {isEditMode ? '수정 완료' : '작성 완료'}
          </Button>
        </div>
      </form>
    </div>
  );
}
