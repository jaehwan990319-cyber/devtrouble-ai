import { apiClient, unwrap } from '../lib/axios';
import type {
  DocumentCreateRequest,
  DocumentDetail,
  DocumentSearchParams,
  DocumentSummary,
  DocumentUpdateRequest,
} from '../types/document';

export const documentService = {
  async search(params: DocumentSearchParams): Promise<DocumentSummary[]> {
    const response = await apiClient.get('/documents', { params });
    return unwrap<DocumentSummary[]>(response);
  },

  async getById(documentId: string): Promise<DocumentDetail> {
    const response = await apiClient.get(`/documents/${documentId}`);
    return unwrap<DocumentDetail>(response);
  },

  async create(request: DocumentCreateRequest): Promise<DocumentDetail> {
    const response = await apiClient.post('/documents', request);
    return unwrap<DocumentDetail>(response);
  },

  async update(documentId: string, request: DocumentUpdateRequest): Promise<DocumentDetail> {
    const response = await apiClient.patch(`/documents/${documentId}`, request);
    return unwrap<DocumentDetail>(response);
  },

  async remove(documentId: string): Promise<void> {
    await apiClient.delete(`/documents/${documentId}`);
  },
};
