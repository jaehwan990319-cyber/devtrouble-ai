"""
RAG 파이프라인 전체를 조립하는 최상위 Service.

PRD AI 기능 7단계 전체 대응:
  1. 질문 분석 → 2. Embedding 생성 → 3. Vector Search →
  4. Top K 문서 검색 → 5. Prompt 생성 → 6. LLM 응답 생성 → 7. 출처 표시

api/v1/ai_search.py는 이 클래스 하나만 호출한다 — Controller가
파이프라인의 세부 구현을 몰라도 되도록 캡슐화하는 것이 목적.

## 그래프 구조 (LangGraph StateGraph)

    classify ──(off-topic)───────────────────► handle_off_topic ─► END
       │
       ▼ (on-topic)
    retrieve ──(결과 충분)───────► rerank ─► generate ─► validate ──(근거 있음)──► END
       ▲   └─(빈약 & 재시도 여력)─► reformulate ┘                        │
       │                              ▲                          (근거 불확실 & 재시도 여력)
       └─(결과 없음 & 재시도 소진)──► handle_no_results ─► END            │
                                       ▲                                │
                                       └────────────────────────────────┘

- **classify**: 트러블슈팅과 무관한 질문(인사/잡담)이면 검색 없이 바로 안내 문구로 끝낸다.
- **retrieve**: 벡터 검색 + 키워드(LIKE) 검색을 함께 수행하는 하이브리드 검색.
- **rerank**: 검색된 청크를 질문과의 관련도 순으로 재정렬한다 (재시도로 이어질 빈약한
  결과는 재랭킹 비용을 안 쓰도록, 결과가 "충분하다"고 판단된 경로에서만 실행된다).
- **generate**: 구조화 출력(with_structured_output)으로 원인/유사사례/해결방법을 받는다.
  스트리밍 시(`stream()`)에는 필드가 채워질 때마다 진행 상황을 커스텀 이벤트로 내보낸다.
- **reformulate**: 검색 결과가 빈약하거나(retrieve 이후) 답변이 근거 불확실하면(validate 이후)
  질문을 재구성해 재시도한다. 두 트리거가 동일한 attempt 예산을 공유한다.
- **validate**: 생성된 답변이 CONTEXT에만 근거했는지 자체 검증한다(self-critique).
"""
import json
import logging
from typing import TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.ai_query_log import AiQueryCitation, AiQueryLog
from app.repositories.document_repository import DocumentRepository
from app.schemas.ai import AiCitation, AiSearchRequest, AiSearchResponse, ConversationMessage
from app.schemas.document import DocumentSearchQuery
from app.services.ai.embedding_service import EmbeddingService
from app.services.ai.llm_client import LlmClient, RagAnswer
from app.services.ai.prompt_builder import PromptBuilder
from app.services.ai.reranker import LlmReranker, Reranker
from app.services.ai.retriever_service import RetrievedChunk, RetrieverService

logger = logging.getLogger(__name__)

# project_id로 필터링할 때, 필터링 후에도 top_k를 채울 여유를 두기 위한 배수
_PROJECT_FILTER_OVERFETCH_FACTOR = 3
# rerank 이후 청크 순위를 relevance_score에 반영할 때 쓰는 감쇠 계수 (1위=1.0, 2위=0.95, ...)
_RERANK_SCORE_STEP = 0.05

_OFF_TOPIC_ANSWER = (
    "저는 개발자 트러블슈팅 관련 질문에 답하기 위한 AI입니다. "
    "겪고 계신 에러나 문제 상황을 구체적으로 질문해 주세요."
)
_NO_RESULT_ANSWER = (
    "관련된 과거 트러블슈팅 문서를 찾지 못했습니다. 질문을 조금 더 구체적으로 입력해 보세요."
)


class _RagState(TypedDict, total=False):
    """LangGraph 노드 간에 주고받는 상태. total=False라 각 노드는 일부 키만 갱신해도 된다."""

    request: AiSearchRequest
    original_query: str
    user_id: str | None
    attempt: int
    on_topic: bool
    chunks: list[RetrievedChunk]
    titles: dict[str, str]
    raw_response: str
    is_grounded: bool
    response: AiSearchResponse


class RagService:
    def __init__(
        self,
        db: Session,
        embedding_service: EmbeddingService,
        retriever_service: RetrieverService,
        prompt_builder: PromptBuilder,
        llm_client: LlmClient,
        reranker: Reranker | None = None,
        settings: Settings | None = None,
    ):
        self.db = db
        self.embedding_service = embedding_service
        self.retriever_service = retriever_service
        self.prompt_builder = prompt_builder
        self.llm_client = llm_client
        self.settings = settings or get_settings()
        self.reranker = reranker or LlmReranker(llm_client)
        self.document_repo = DocumentRepository(db)
        self._graph = self._build_graph()

    def search(self, request: AiSearchRequest, user_id: str | None) -> AiSearchResponse:
        result: _RagState = self._graph.invoke(self._initial_state(request, user_id))
        return result["response"]

    def stream(self, request: AiSearchRequest, user_id: str | None):
        """
        그래프 진행 상황을 (event_name, payload) 튜플로 순서대로 낸다.

        - 노드가 끝날 때마다 (node_name, 그 노드가 갱신한 상태 dict)
        - generate 노드 실행 "도중"에는 ("token", {"partial_answer": "..."})로
          부분적으로 채워지는 답변을 추가로 낸다 (LangGraph custom stream 이벤트).

        api/v1/ai_search.py의 스트리밍 엔드포인트가 이걸 그대로 SSE 이벤트로 변환한다.
        """
        initial_state = self._initial_state(request, user_id)
        for stream_type, chunk in self._graph.stream(initial_state, stream_mode=["updates", "custom"]):
            if stream_type == "custom":
                yield "token", chunk
            else:
                for node_name, partial_state in chunk.items():
                    # 노드가 상태 변경 없이 빈 dict({})를 반환하면, LangGraph의 "updates"
                    # 스트림 모드는 이를 None으로 보고한다 (예: condense가 history 없어서
                    # 아무것도 안 바꿀 때). 소비하는 쪽이 항상 dict를 받도록 여기서 방어한다.
                    yield node_name, partial_state or {}

    @staticmethod
    def _initial_state(request: AiSearchRequest, user_id: str | None) -> _RagState:
        return {
            "request": request,
            "original_query": request.query,
            "user_id": user_id,
            "attempt": 0,
        }

    # --- LangGraph 그래프 정의 ---

    def _build_graph(self):
        graph = StateGraph(_RagState)
        graph.add_node("condense", self._condense_node)
        graph.add_node("classify", self._classify_node)
        graph.add_node("retrieve", self._retrieve_node)
        graph.add_node("rerank", self._rerank_node)
        graph.add_node("reformulate", self._reformulate_node)
        graph.add_node("generate", self._generate_node)
        graph.add_node("validate", self._validate_node)
        graph.add_node("handle_no_results", self._handle_no_results_node)
        graph.add_node("handle_off_topic", self._handle_off_topic_node)

        graph.set_entry_point("condense")
        graph.add_edge("condense", "classify")
        graph.add_conditional_edges("classify", self._route_after_classify)
        graph.add_conditional_edges("retrieve", self._route_after_retrieve)
        graph.add_edge("rerank", "generate")
        graph.add_edge("reformulate", "retrieve")
        graph.add_edge("generate", "validate")
        graph.add_conditional_edges("validate", self._route_after_validate)
        graph.add_edge("handle_no_results", END)
        graph.add_edge("handle_off_topic", END)
        return graph.compile()

    def _route_after_classify(self, state: _RagState) -> str:
        return "retrieve" if state.get("on_topic", True) else "handle_off_topic"

    def _route_after_retrieve(self, state: _RagState) -> str:
        chunks = state.get("chunks") or []
        attempt = state.get("attempt", 0)
        has_retry_budget = attempt < self.settings.RAG_MAX_RETRIEVAL_ATTEMPTS

        if chunks and self._top_score(chunks) >= self.settings.RAG_RETRY_SCORE_THRESHOLD:
            return "rerank"
        if has_retry_budget:
            return "reformulate"
        return "rerank" if chunks else "handle_no_results"

    def _route_after_validate(self, state: _RagState) -> str:
        attempt = state.get("attempt", 0)
        if state.get("is_grounded", True):
            return END
        if attempt < self.settings.RAG_MAX_RETRIEVAL_ATTEMPTS:
            return "reformulate"
        return END  # 재시도 예산 소진 — 근거 불확실한 채로 그냥 반환한다 (response.is_grounded=False)

    # --- 노드 구현 ---

    def _condense_node(self, state: _RagState) -> dict:
        """
        멀티턴 후속 질문("그럼 그건요?")을 대화 맥락 없이도 이해되는 완전한 질문으로
        압축한다. 이전에는 history가 generate 프롬프트에만 반영되고 검색(retrieve)은
        항상 짧은 후속 질문 그대로 수행돼서, 검색이 엉뚱한 문서를 찾는 문제가 있었다 —
        이 노드가 그 문제를 해결한다.

        history가 없으면(첫 질문) LLM 호출 자체를 하지 않는다 (불필요한 비용 방지).
        """
        request = state["request"]
        if not request.history or not self.settings.RAG_ENABLE_QUERY_CONDENSATION:
            return {}

        condensed_query = self.llm_client.condense_query(
            request.query, self._format_history(request.history)
        )
        logger.info("질문 압축: %r -> %r", request.query, condensed_query)

        new_request = request.model_copy(update={"query": condensed_query})
        return {"request": new_request}

    def _classify_node(self, state: _RagState) -> dict:
        """질문이 트러블슈팅과 무관하면(인사/잡담) 검색 자체를 건너뛴다."""
        if not self.settings.RAG_ENABLE_CLASSIFY:
            return {"on_topic": True}
        on_topic = self.llm_client.classify(state["request"].query)
        return {"on_topic": on_topic}

    def _handle_off_topic_node(self, state: _RagState) -> dict:
        return {"response": AiSearchResponse(answer=_OFF_TOPIC_ANSWER, citations=[], on_topic=False)}

    def _retrieve_node(self, state: _RagState) -> dict:
        """PRD 1~4단계: 질문 분석 → Embedding → Vector Search → Top-K 문서 검색 (+ 키워드 검색 보완)."""
        chunks = self._retrieve_chunks(state["request"])
        titles = self._fetch_titles(chunks) if chunks else {}
        return {"chunks": chunks, "titles": titles}

    def _rerank_node(self, state: _RagState) -> dict:
        """검색된 청크를 질문과의 관련도 순으로 재정렬한다 (settings.RERANK_PROVIDER로 벤더 선택)."""
        chunks = state["chunks"]
        if not self.settings.RAG_ENABLE_RERANK:
            return {}

        chunk_texts = [c.chunk_text for c in chunks]
        order = self.reranker.rerank(state["request"].query, chunk_texts)

        reranked = [
            RetrievedChunk(
                document_id=chunks[rank].document_id,
                chunk_text=chunks[rank].chunk_text,
                relevance_score=max(1.0 - i * _RERANK_SCORE_STEP, 0.0),
            )
            for i, rank in enumerate(order)
        ]
        return {"chunks": reranked}

    def _reformulate_node(self, state: _RagState) -> dict:
        """검색 결과가 빈약하거나 답변 근거가 불확실할 때 질문을 재구성하고 attempt를 늘린다."""
        current_query = state["request"].query
        new_query = self.llm_client.reformulate(current_query)
        attempt = state.get("attempt", 0) + 1

        logger.info(
            "RAG 재검색 시도 %d/%d: %r -> %r",
            attempt, self.settings.RAG_MAX_RETRIEVAL_ATTEMPTS, current_query, new_query,
        )

        new_request = state["request"].model_copy(update={"query": new_query})
        return {"request": new_request, "attempt": attempt}

    def _handle_no_results_node(self, state: _RagState) -> dict:
        return {"response": AiSearchResponse(answer=_NO_RESULT_ANSWER, citations=[])}

    def _generate_node(self, state: _RagState) -> dict:
        """
        PRD 5~7단계: Prompt 생성(대화 이력 포함) → 구조화 출력으로 LLM 응답 생성 → 출처 표시.

        get_stream_writer()는 .invoke()로 실행될 때는 안전한 no-op이고, .stream()으로
        실행될 때만 실제로 "token" 커스텀 이벤트를 내보낸다 — 그래서 이 노드 코드는
        스트리밍 여부와 무관하게 하나로 통일할 수 있다.
        """
        request = state["request"]
        chunks = state["chunks"]
        titles = state["titles"]
        history = self._format_history(request.history)
        writer = get_stream_writer()

        messages = self.prompt_builder.build(request.query, chunks, titles, history=history)

        structured: RagAnswer | None = None
        for partial in self.llm_client.stream_structured(messages):
            structured = partial
            writer({"partial_answer": self._compose_answer(partial)})

        if structured is None:
            structured = RagAnswer()

        answer = self._compose_answer(structured)
        citations = self._build_citations(chunks, titles)
        raw_response = structured.model_dump_json()

        response = AiSearchResponse(
            answer=answer,
            cause=structured.cause,
            similar_cases=structured.similar_cases,
            solution=structured.solution,
            citations=citations,
        )
        return {"raw_response": raw_response, "response": response}

    def _validate_node(self, state: _RagState) -> dict:
        """생성된 답변이 CONTEXT에만 근거했는지 자체 검증한다 (self-critique)."""
        if not self.settings.RAG_ENABLE_VALIDATION:
            response = state["response"].model_copy(update={"is_grounded": True})
            self._log_query(
                state.get("user_id"), state["original_query"], state["raw_response"], response.citations
            )
            return {"is_grounded": True, "response": response}

        context_json = json.dumps(
            [{"document_id": c.document_id, "text": c.chunk_text} for c in state["chunks"]],
            ensure_ascii=False,
        )
        is_grounded = self.llm_client.check_grounded(state["raw_response"], context_json)

        response = state["response"].model_copy(update={"is_grounded": is_grounded})

        # 최종 확정(END로 갈 때)에만 감사 로그를 남긴다 — 재시도 예산 소진 여부와 무관하게
        # 여기서 그래프가 끝나므로, 로그는 여기 한 곳에서만 남기면 중복이 없다.
        attempt = state.get("attempt", 0)
        if is_grounded or attempt >= self.settings.RAG_MAX_RETRIEVAL_ATTEMPTS:
            self._log_query(
                state.get("user_id"), state["original_query"], state["raw_response"], response.citations
            )

        return {"is_grounded": is_grounded, "response": response}

    # --- 내부 헬퍼 ---

    @staticmethod
    def _compose_answer(structured: RagAnswer) -> str:
        parts = [
            f"[{label}] {value}"
            for label, value in (
                ("원인", structured.cause),
                ("유사 사례", structured.similar_cases),
                ("해결 방법", structured.solution),
            )
            if value
        ]
        return "\n\n".join(parts)

    @staticmethod
    def _format_history(history: list[ConversationMessage]) -> list[dict[str, str]]:
        return [{"role": turn.role, "content": turn.content} for turn in history]

    @staticmethod
    def _top_score(chunks: list[RetrievedChunk]) -> float:
        return max((c.relevance_score for c in chunks), default=0.0)

    def _retrieve_chunks(self, request: AiSearchRequest) -> list[RetrievedChunk]:
        vector_chunks = self._vector_search(request)
        keyword_chunks = self._keyword_search(request)
        return self._merge_chunks(vector_chunks, keyword_chunks)

    def _vector_search(self, request: AiSearchRequest) -> list[RetrievedChunk]:
        query_embedding = self.embedding_service.embed_texts([request.query])[0]

        if request.project_id:
            # VectorStore는 메타데이터 필터링을 지원하지 않으므로 넉넉히 가져온 뒤
            # 애플리케이션 레벨에서 project_id로 걸러낸다.
            over_fetch = self.settings.RAG_TOP_K * _PROJECT_FILTER_OVERFETCH_FACTOR
            candidates = self.retriever_service.search(query_embedding, top_k=over_fetch)
            candidate_doc_ids = {c.document_id for c in candidates}
            project_doc_ids = {
                d.id for d in self.document_repo.list_by_ids(list(candidate_doc_ids))
                if d.project_id == request.project_id
            }
            return [c for c in candidates if c.document_id in project_doc_ids]

        return self.retriever_service.search(query_embedding, top_k=self.settings.RAG_TOP_K)

    def _keyword_search(self, request: AiSearchRequest) -> list[RetrievedChunk]:
        """
        하이브리드 검색: 벡터 임베딩이 놓치기 쉬운 정확한 용어(에러 코드 등) 매칭을
        LIKE 기반 키워드 검색으로 보완한다. FR-SEARCH-01/03에서 쓰던 것과 같은 검색이다.
        """
        query = DocumentSearchQuery(keyword=request.query, project_id=request.project_id)
        documents = self.document_repo.search(query)[: self.settings.RAG_TOP_K]

        return [
            RetrievedChunk(
                document_id=doc.id,
                chunk_text=doc.problem_description,
                relevance_score=self.settings.RAG_KEYWORD_MATCH_SCORE,
            )
            for doc in documents
        ]

    def _merge_chunks(
        self, vector_chunks: list[RetrievedChunk], keyword_chunks: list[RetrievedChunk]
    ) -> list[RetrievedChunk]:
        """문서 단위로 중복 제거하고, 같은 문서가 양쪽에서 나오면 더 높은 점수를 취한다."""
        best_by_doc: dict[str, RetrievedChunk] = {}
        for chunk in [*vector_chunks, *keyword_chunks]:
            existing = best_by_doc.get(chunk.document_id)
            if existing is None or chunk.relevance_score > existing.relevance_score:
                best_by_doc[chunk.document_id] = chunk

        merged = sorted(best_by_doc.values(), key=lambda c: c.relevance_score, reverse=True)
        return merged[: self.settings.RAG_TOP_K]

    def _fetch_titles(self, chunks: list[RetrievedChunk]) -> dict[str, str]:
        document_ids = list(dict.fromkeys(c.document_id for c in chunks))
        documents = self.document_repo.list_by_ids(document_ids)
        return {d.id: d.title for d in documents}

    @staticmethod
    def _build_citations(chunks: list[RetrievedChunk], titles: dict[str, str]) -> list[AiCitation]:
        """같은 문서의 여러 청크가 검색됐다면 가장 관련도 높은 점수 하나로 통합한다."""
        best_score_by_doc: dict[str, float] = {}
        for chunk in chunks:
            current = best_score_by_doc.get(chunk.document_id)
            if current is None or chunk.relevance_score > current:
                best_score_by_doc[chunk.document_id] = chunk.relevance_score

        citations = [
            AiCitation(document_id=doc_id, title=titles.get(doc_id, ""), relevance_score=score)
            for doc_id, score in best_score_by_doc.items()
        ]
        citations.sort(key=lambda c: c.relevance_score, reverse=True)
        return citations

    def _log_query(
        self, user_id: str | None, query_text: str, response_text: str, citations: list[AiCitation]
    ) -> None:
        """FR-AI-05 추적 및 분석용 감사 로그. 로깅 실패가 검색 응답을 막아서는 안 된다."""
        try:
            log = AiQueryLog(user_id=user_id, query_text=query_text, response_text=response_text)
            self.db.add(log)
            self.db.flush()

            for citation in citations:
                self.db.add(
                    AiQueryCitation(
                        ai_query_log_id=log.id,
                        document_id=citation.document_id,
                        relevance_score=citation.relevance_score,
                    )
                )
            self.db.commit()
        except Exception:
            logger.exception("AI 질의 로그 기록에 실패했습니다.")
            self.db.rollback()
