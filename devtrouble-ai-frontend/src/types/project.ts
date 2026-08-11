export interface Project {
  id: string;
  owner_id: string | null;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreateRequest {
  name: string;
  description?: string;
}

export type ProjectUpdateRequest = Partial<ProjectCreateRequest>;
