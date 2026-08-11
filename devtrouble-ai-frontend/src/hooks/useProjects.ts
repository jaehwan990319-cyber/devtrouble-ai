import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { projectService } from '../services/projectService';
import type { ProjectCreateRequest, ProjectUpdateRequest } from '../types/project';

const projectKeys = {
  all: ['projects'] as const,
  mine: () => [...projectKeys.all, 'mine'] as const,
  detail: (id: string) => [...projectKeys.all, 'detail', id] as const,
};

export function useMyProjects() {
  return useQuery({
    queryKey: projectKeys.mine(),
    queryFn: () => projectService.listMine(),
  });
}

export function useProject(projectId: string | undefined) {
  return useQuery({
    queryKey: projectKeys.detail(projectId ?? ''),
    queryFn: () => projectService.getById(projectId as string),
    enabled: Boolean(projectId),
  });
}

export function useCreateProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: ProjectCreateRequest) => projectService.create(request),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: projectKeys.all });
    },
  });
}

export function useUpdateProject(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: ProjectUpdateRequest) => projectService.update(projectId, request),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: projectKeys.all });
    },
  });
}

export function useDeleteProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (projectId: string) => projectService.remove(projectId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: projectKeys.all });
    },
  });
}
