import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { commentService } from '../services/commentService';
import type { CommentCreateRequest } from '../types/comment';

const commentKeys = {
  byDocument: (documentId: string) => ['comments', documentId] as const,
};

export function useComments(documentId: string | undefined) {
  return useQuery({
    queryKey: commentKeys.byDocument(documentId ?? ''),
    queryFn: () => commentService.list(documentId as string),
    enabled: Boolean(documentId),
  });
}

export function useAddComment(documentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: CommentCreateRequest) => commentService.add(documentId, request),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: commentKeys.byDocument(documentId) });
    },
  });
}

export function useDeleteComment(documentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (commentId: string) => commentService.remove(documentId, commentId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: commentKeys.byDocument(documentId) });
    },
  });
}
