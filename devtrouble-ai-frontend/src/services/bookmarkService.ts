import { apiClient, unwrap } from '../lib/axios';
import type { BookmarkToggleResponse } from '../types/bookmark';

export const bookmarkService = {
  async listBookmarkedDocumentIds(): Promise<string[]> {
    const response = await apiClient.get('/bookmarks');
    return unwrap<string[]>(response);
  },

  async toggle(documentId: string): Promise<BookmarkToggleResponse> {
    const response = await apiClient.post(`/bookmarks/${documentId}`);
    return unwrap<BookmarkToggleResponse>(response);
  },

  async recordView(documentId: string): Promise<void> {
    await apiClient.post(`/bookmarks/recent-views/${documentId}`);
  },

  async listRecentViewDocumentIds(): Promise<string[]> {
    const response = await apiClient.get('/bookmarks/recent-views');
    return unwrap<string[]>(response);
  },
};
