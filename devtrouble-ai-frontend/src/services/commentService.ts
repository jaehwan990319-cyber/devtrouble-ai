import { apiClient, unwrap } from '../lib/axios';
import type { Comment, CommentCreateRequest } from '../types/comment';

export const commentService = {
  async list(documentId: string): Promise<Comment[]> {
    const response = await apiClient.get(`/documents/${documentId}/comments`);
    return unwrap<Comment[]>(response);
  },

  async add(documentId: string, request: CommentCreateRequest): Promise<Comment> {
    const response = await apiClient.post(`/documents/${documentId}/comments`, request);
    return unwrap<Comment>(response);
  },

  async remove(documentId: string, commentId: string): Promise<void> {
    await apiClient.delete(`/documents/${documentId}/comments/${commentId}`);
  },
};
