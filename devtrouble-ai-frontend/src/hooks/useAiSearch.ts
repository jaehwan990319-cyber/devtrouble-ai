import { useCallback, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { aiService } from '../services/aiService';
import type { AiSearchRequest, AiSearchResponse } from '../types/ai';

export function useAiSearch() {
  return useMutation({
    mutationFn: (request: AiSearchRequest) => aiService.search(request),
  });
}

interface UseAiSearchStreamResult {
  run: (request: AiSearchRequest) => Promise<AiSearchResponse>;
  stage: string | null;
  /** generate 단계에서 점점 채워지는 답변 미리보기. "token" 이벤트가 없었다면 null. */
  partialAnswer: string | null;
  isStreaming: boolean;
  error: Error | null;
}

/**
 * /ai/search/stream을 소비하면서, 지금 그래프가 어느 노드를 지나고 있는지(stage)와
 * 답변이 실시간으로 채워지는 과정(partialAnswer)을 함께 노출하는 훅.
 * React Query의 useMutation은 스트리밍 중간 상태를 다루기 부적합해서(성공/실패 두 상태뿐),
 * 여기서는 일반 useState로 직접 관리한다.
 */
export function useAiSearchStream(): UseAiSearchStreamResult {
  const [stage, setStage] = useState<string | null>(null);
  const [partialAnswer, setPartialAnswer] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const run = useCallback(async (request: AiSearchRequest): Promise<AiSearchResponse> => {
    setIsStreaming(true);
    setError(null);
    setStage(null);
    setPartialAnswer(null);

    try {
      for await (const event of aiService.searchStream(request)) {
        setStage(event.stage);
        if (event.stage === 'token' && event.answer !== undefined) {
          setPartialAnswer(event.answer);
        }
        if (event.stage === 'done' && event.response) {
          return event.response;
        }
      }
      throw new Error('스트리밍이 완료되지 않고 끝났습니다.');
    } catch (err) {
      const normalized = err instanceof Error ? err : new Error('AI 검색 스트리밍에 실패했습니다.');
      setError(normalized);
      throw normalized;
    } finally {
      setIsStreaming(false);
      setStage(null);
      setPartialAnswer(null);
    }
  }, []);

  return { run, stage, partialAnswer, isStreaming, error };
}
