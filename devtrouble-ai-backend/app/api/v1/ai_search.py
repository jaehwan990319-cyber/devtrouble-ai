import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import DbSession
from app.core.config import get_settings
from app.schemas.ai import AiSearchRequest, AiSearchResponse
from app.schemas.common import ApiResponse
from app.services.ai.embedding_provider import get_embedding_provider
from app.services.ai.embedding_service import EmbeddingService
from app.services.ai.llm_client import get_llm_client
from app.services.ai.prompt_builder import PromptBuilder
from app.services.ai.rag_service import RagService
from app.services.ai.reranker import get_reranker
from app.services.ai.retriever_service import RetrieverService
from app.services.ai.vector_store import get_vector_store

router = APIRouter(prefix="/ai", tags=["ai"])

# 그래프 상태 전체를 이벤트로 스트리밍하면 내부 구현(청크 원문 등)이 그대로 노출된다.
# 프론트에는 "지금 어느 단계인지"와, 최종 단계에서만 실제 응답을 담아 보낸다.
_STREAMABLE_NODES = {"condense", "classify", "retrieve", "rerank", "reformulate", "generate", "validate"}


def get_rag_service(db: DbSession) -> RagService:
    """
    RAG 파이프라인 컴포넌트 조립 지점 (Composition Root).

    settings.AI_PROVIDER / settings.VECTOR_DB_PROVIDER / settings.RERANK_PROVIDER 값에 따라
    운영용(OpenAI·watsonx / Qdrant·Chroma / Cohere) 또는 오프라인 폴백(로컬 해시 임베딩/
    템플릿 LLM/FAISS/LLM 기반 재랭킹) 구현체가 자동으로 선택된다
    (embedding_provider.py, llm_client.py, vector_store.py, reranker.py 참고).
    """
    settings = get_settings()
    provider = get_embedding_provider(settings)
    vector_store = get_vector_store(provider.dimension, settings)
    llm_client = get_llm_client(settings)

    return RagService(
        db=db,
        embedding_service=EmbeddingService(db=db, provider=provider, vector_store=vector_store),
        retriever_service=RetrieverService(db=db, provider=provider, vector_store=vector_store),
        prompt_builder=PromptBuilder(),
        llm_client=llm_client,
        reranker=get_reranker(llm_client, settings),
        settings=settings,
    )


@router.post("/search", response_model=ApiResponse[AiSearchResponse])
def ai_search(request: AiSearchRequest, db: DbSession, rag_service: RagService = Depends(get_rag_service)):
    # 로그인 없이도 사용 가능하도록 user_id는 optional로 둔다.
    # (인증이 필요하면 CurrentUser로 교체)
    result = rag_service.search(request, user_id=None)
    return ApiResponse.ok(result)


@router.post("/search/stream")
def ai_search_stream(
    request: AiSearchRequest, db: DbSession, rag_service: RagService = Depends(get_rag_service)
):
    """
    Server-Sent Events로 그래프 진행 상황을 실시간으로 보낸다.

    - 노드가 끝날 때마다 `data: {"stage": "<노드명>"}\\n\\n`
    - generate 노드가 실행되는 "도중"에는 `data: {"stage": "token", "answer": "..."}\\n\\n`으로
      점점 채워지는 답변을 추가로 보낸다 (진짜 챗봇처럼 타이핑되는 효과를 위한 것).
    - 마지막에 `data: {"stage": "done", "response": {...}}\\n\\n`으로 최종 응답을 보낸다.

    프론트는 EventSource 또는 fetch + ReadableStream으로 읽으면 된다.
    """

    def event_stream_with_result():
        final_response: AiSearchResponse | None = None
        for node_name, partial_state in rag_service.stream(request, user_id=None):
            if node_name == "token":
                payload = {"stage": "token", "answer": partial_state.get("partial_answer", "")}
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            elif node_name in _STREAMABLE_NODES:
                yield f"data: {json.dumps({'stage': node_name}, ensure_ascii=False)}\n\n"

            if "response" in partial_state:
                final_response = partial_state["response"]

        payload = {"stage": "done", "response": final_response.model_dump() if final_response else None}
        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream_with_result(), media_type="text/event-stream")
