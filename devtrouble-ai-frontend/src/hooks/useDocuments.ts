import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { documentService } from '../services/documentService';
import type { DocumentCreateRequest, DocumentSearchParams, DocumentUpdateRequest } from '../types/document';

const documentKeys = {
  all: ['documents'] as const,
  search: (params: DocumentSearchParams) => [...documentKeys.all, 'search', params] as const,
  detail: (id: string) => [...documentKeys.all, 'detail', id] as const,
};

export function useDocumentSearch(params: DocumentSearchParams) {
  return useQuery({
    queryKey: documentKeys.search(params),
    queryFn: () => documentService.search(params),
  });
}

export function useDocument(documentId: string | undefined) {
  return useQuery({
    queryKey: documentKeys.detail(documentId ?? ''),
    queryFn: () => documentService.getById(documentId as string),
    enabled: Boolean(documentId),
  });
}

export function useCreateDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: DocumentCreateRequest) => documentService.create(request),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: documentKeys.all });
    },
  });
}

export function useUpdateDocument(documentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: DocumentUpdateRequest) => documentService.update(documentId, request),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: documentKeys.all });
    },
  });
}

export function useDeleteDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (documentId: string) => documentService.remove(documentId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: documentKeys.all });
    },
  });
}
