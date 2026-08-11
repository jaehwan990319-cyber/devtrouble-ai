import { API_BASE_URL, apiClient, unwrap } from '../lib/axios';
import type { AiSearchRequest, AiSearchResponse, AiSearchStreamEvent } from '../types/ai';

export const aiService = {
  async search(request: AiSearchRequest): Promise<AiSearchResponse> {
    const response = await apiClient.post('/ai/search', request);
    return unwrap<AiSearchResponse>(response);
  },

  /**
   * /ai/search/stream(SSE)을 순서대로 소비하는 async generator.
   * axios는 브라우저에서 스트리밍 응답을 다루기 번거로워서, 이 호출만 fetch를 직접 쓴다
   * (이 엔드포인트는 인증이 필요 없으므로 axios 인터셉터의 토큰 첨부 로직도 필요 없다).
   */
  async *searchStream(request: AiSearchRequest): AsyncGenerator<AiSearchStreamEvent> {
    const response = await fetch(`${API_BASE_URL}/ai/search/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });

    if (!response.ok || !response.body) {
      throw new Error('AI 검색 스트리밍 요청에 실패했습니다.');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split('\n\n');
      buffer = events.pop() ?? ''; // 아직 완결되지 않은 마지막 조각은 다음 루프로 넘긴다.

      for (const rawEvent of events) {
        const line = rawEvent.trim();
        if (!line.startsWith('data: ')) continue;
        yield JSON.parse(line.slice('data: '.length)) as AiSearchStreamEvent;
      }
    }
  },
};
