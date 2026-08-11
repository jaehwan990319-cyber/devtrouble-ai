import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { bookmarkService } from '../services/bookmarkService';

const bookmarkKeys = {
  mine: ['bookmarks'] as const,
  recentViews: ['recent-views'] as const,
};

export function useMyBookmarkedIds() {
  return useQuery({
    queryKey: bookmarkKeys.mine,
    queryFn: () => bookmarkService.listBookmarkedDocumentIds(),
  });
}

export function useToggleBookmark() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (documentId: string) => bookmarkService.toggle(documentId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: bookmarkKeys.mine });
    },
  });
}

export function useRecordRecentView() {
  return useMutation({
    mutationFn: (documentId: string) => bookmarkService.recordView(documentId),
  });
}

export function useRecentViewIds() {
  return useQuery({
    queryKey: bookmarkKeys.recentViews,
    queryFn: () => bookmarkService.listRecentViewDocumentIds(),
  });
}
