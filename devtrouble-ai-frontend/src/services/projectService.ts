import { apiClient, unwrap } from '../lib/axios';
import type { Project, ProjectCreateRequest, ProjectUpdateRequest } from '../types/project';

export const projectService = {
  async listMine(): Promise<Project[]> {
    const response = await apiClient.get('/projects');
    return unwrap<Project[]>(response);
  },

  async getById(projectId: string): Promise<Project> {
    const response = await apiClient.get(`/projects/${projectId}`);
    return unwrap<Project>(response);
  },

  async create(request: ProjectCreateRequest): Promise<Project> {
    const response = await apiClient.post('/projects', request);
    return unwrap<Project>(response);
  },

  async update(projectId: string, request: ProjectUpdateRequest): Promise<Project> {
    const response = await apiClient.patch(`/projects/${projectId}`, request);
    return unwrap<Project>(response);
  },

  async remove(projectId: string): Promise<void> {
    await apiClient.delete(`/projects/${projectId}`);
  },
};
