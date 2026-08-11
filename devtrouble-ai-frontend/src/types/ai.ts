export interface ConversationMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface AiSearchRequest {
  query: string;
  project_id?: string;
  /** 이전 턴들. 서버는 대화를 저장하지 않으므로 매번 지금까지의 대화를 그대로 실어 보낸다. */
  history?: ConversationMessage[];
}

export interface AiCitation {
  document_id: string;
  title: string;
  relevance_score: number;
}

export interface AiSearchResponse {
  answer: string;
  cause: string | null;
  similar_cases: string | null;
  solution: string | null;
  citations: AiCitation[];
  /** 트러블슈팅과 무관한 질문(인사/잡담)으로 분류되었는지. false면 검색 없이 안내만 반환된 것. */
  on_topic: boolean;
  /** 답변이 검색된 문서에 실제로 근거했다고 자체 검증됐는지. false면 확신도가 낮을 수 있음. */
  is_grounded: boolean;
}

/** /ai/search/stream(SSE)이 보내는 이벤트. stage="token"일 때 answer(부분 답변), "done"일 때 response가 채워진다. */
export interface AiSearchStreamEvent {
  stage: string;
  answer?: string;
  response?: AiSearchResponse;
}
