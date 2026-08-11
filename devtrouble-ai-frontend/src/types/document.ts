export interface DocumentSummary {
  id: string;
  project_id: string;
  title: string;
  view_count: number;
  created_at: string;
  tag_names: string[];
}

export interface DocumentDetail {
  id: string;
  project_id: string;
  author_id: string | null;
  title: string;
  problem_description: string;
  error_message: string | null;
  stack_trace: string | null;
  solution: string | null;
  retrospective: string | null;
  view_count: number;
  created_at: string;
  updated_at: string;
  tag_names: string[];
}

export interface DocumentCreateRequest {
  project_id: string;
  title: string;
  problem_description: string;
  error_message?: string;
  stack_trace?: string;
  solution?: string;
  retrospective?: string;
  tag_names?: string[];
}

export type DocumentUpdateRequest = Partial<Omit<DocumentCreateRequest, 'project_id'>>;

export interface DocumentSearchParams {
  keyword?: string;
  tag?: string;
  error_code?: string;
  project_id?: string;
}
