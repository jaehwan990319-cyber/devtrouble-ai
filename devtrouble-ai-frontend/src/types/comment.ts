export interface Comment {
  id: string;
  document_id: string;
  author_id: string | null;
  content: string;
}

export interface CommentCreateRequest {
  content: string;
}
