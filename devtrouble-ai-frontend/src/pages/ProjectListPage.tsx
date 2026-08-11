import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '../components/Button';
import { EmptyState, ErrorBanner, Spinner } from '../components/Feedback';
import { Input } from '../components/FormField';
import { useCreateProject, useDeleteProject, useMyProjects } from '../hooks/useProjects';
import { ApiError } from '../types/api';

export function ProjectListPage() {
  const { data: projects, isLoading, isError } = useMyProjects();
  const createProject = useCreateProject();
  const deleteProject = useDeleteProject();

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    try {
      await createProject.mutateAsync({ name, description: description || undefined });
      setName('');
      setDescription('');
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : '프로젝트 생성에 실패했습니다.');
    }
  }

  async function handleDelete(projectId: string) {
    if (!window.confirm('이 프로젝트를 삭제하시겠습니까? 소속된 문서도 함께 정리됩니다.')) return;
    await deleteProject.mutateAsync(projectId);
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">내 프로젝트</h1>
        <p className="mt-1 text-sm text-slate-500">
          트러블슈팅 문서는 프로젝트 단위로 관리됩니다. 먼저 프로젝트를 만들어 주세요.
        </p>
      </div>

      <form
        onSubmit={(e) => void handleCreate(e)}
        className="flex flex-col gap-3 rounded-lg border border-slate-200 bg-white p-4 sm:flex-row sm:items-end"
      >
        {formError && (
          <div className="sm:w-full">
            <ErrorBanner message={formError} />
          </div>
        )}
        <div className="flex-1">
          <Input
            label="프로젝트 이름"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="예: 결제 시스템 리팩토링"
          />
        </div>
        <div className="flex-1">
          <Input
            label="설명 (선택)"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>
        <Button type="submit" isLoading={createProject.isPending}>
          프로젝트 만들기
        </Button>
      </form>

      {isLoading && (
        <div className="flex justify-center py-12">
          <Spinner />
        </div>
      )}

      {isError && <ErrorBanner message="프로젝트 목록을 불러오지 못했습니다." />}

      {projects && projects.length === 0 && <EmptyState message="아직 프로젝트가 없습니다." />}

      {projects && projects.length > 0 && (
        <ul className="flex flex-col gap-3">
          {projects.map((project) => (
            <li
              key={project.id}
              className="flex items-start justify-between gap-4 rounded-lg border border-slate-200 bg-white p-4"
            >
              <div>
                <h2 className="font-semibold text-slate-900">{project.name}</h2>
                {project.description && <p className="mt-1 text-sm text-slate-500">{project.description}</p>}
                <Link
                  to={`/documents?project_id=${project.id}`}
                  className="mt-2 inline-block text-xs text-brand-600 hover:underline"
                >
                  이 프로젝트의 문서 보기 →
                </Link>
              </div>
              <Button
                variant="danger"
                onClick={() => void handleDelete(project.id)}
                isLoading={deleteProject.isPending}
              >
                삭제
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
