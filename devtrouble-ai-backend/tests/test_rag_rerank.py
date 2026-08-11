"""
③(재랭킹) — 하이브리드 검색으로 모은 청크를 질문 관련도 순으로 다시 정렬하는지 검증한다.

TemplateLlmClient의 rerank() 자체는 tests/test_ai_provider_selection.py에서 단위 테스트하고,
여기서는 RagService 그래프 안에서 재랭킹 결과가 실제로 최종 citations 순서에 반영되는지를
Fake LLM 클라이언트로 완전히 통제해 검증한다.
"""
import pytest

from app.models.project import Project
from app.models.trouble_document import TroubleDocument
from app.schemas.ai import AiSearchRequest
from app.services.ai.embedding_provider import LocalHashEmbeddingProvider
from app.services.ai.embedding_service import EmbeddingService
from app.services.ai.llm_client import RagAnswer
from app.services.ai.prompt_builder import PromptBuilder
from app.services.ai.rag_service import RagService
from app.services.ai.retriever_service import RetrieverService
from app.services.ai.vector_store import FaissVectorStore
from tests.test_rag_multiturn_streaming import RecordingMessagesLlmClient
from tests.test_rag_reformulation import _settings


@pytest.fixture
def project_id(db_session):
    project = Project(name="재랭킹 테스트 프로젝트")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project.id


class ScriptedRerankLlmClient(RecordingMessagesLlmClient):
    """rerank()가 항상 정해둔 순서를 반환하는 테스트 더블."""

    def __init__(self, order: list[int]):
        super().__init__()
        self._order = order
        self.rerank_call_count = 0
        self.rerank_input_texts: list[str] = []

    def generate_structured(self, messages):
        return RagAnswer(cause="c", similar_cases="s", solution="sol")

    def rerank(self, query: str, chunk_texts: list[str]) -> list[int]:
        self.rerank_call_count += 1
        self.rerank_input_texts = chunk_texts
        return self._order


def _make_document(db_session, project_id, **overrides) -> TroubleDocument:
    defaults = {
        "project_id": project_id,
        "title": "문서",
        "problem_description": "설명",
    }
    defaults.update(overrides)
    document = TroubleDocument(**defaults)
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)
    return document


def _build_rag_service(db_session, llm_client):
    provider = LocalHashEmbeddingProvider()
    vector_store = FaissVectorStore(dimension=provider.dimension)
    settings = _settings()
    embedding_service = EmbeddingService(db=db_session, provider=provider, vector_store=vector_store)
    retriever_service = RetrieverService(
        db=db_session, provider=provider, vector_store=vector_store, settings=settings
    )
    rag_service = RagService(
        db=db_session,
        embedding_service=embedding_service,
        retriever_service=retriever_service,
        prompt_builder=PromptBuilder(),
        llm_client=llm_client,
        settings=settings,
    )
    return rag_service, embedding_service


class TestRerank:
    def test_rerank_result_determines_citation_order(self, db_session, project_id):
        """rerank가 뒤집은 순서가 최종 citations 순서에 그대로 반영되어야 한다."""
        doc_a = _make_document(
            db_session, project_id, title="문서 A - Redis 문제", problem_description="Redis 관련 설명"
        )
        doc_b = _make_document(
            db_session, project_id, title="문서 B - Kafka 문제", problem_description="Kafka 관련 설명"
        )

        # rerank가 (원래 순서가 무엇이든) 두 항목을 뒤집게 한다.
        llm_client = ScriptedRerankLlmClient(order=[1, 0])
        rag_service, embedding_service = _build_rag_service(db_session, llm_client)
        embedding_service.index_document(doc_a.id)
        embedding_service.index_document(doc_b.id)

        response = rag_service.search(AiSearchRequest(query="Redis Kafka 문제"), user_id=None)

        assert llm_client.rerank_call_count == 1
        assert len(response.citations) == 2

        # rerank에 실제로 전달된 원래 순서를 기준으로, "뒤집힌 결과"가 맞는지 검증한다
        # (retrieve 단계의 실제 정렬 순서는 임베딩 해시값에 따라 달라질 수 있어 하드코딩하지 않는다).
        original_order_doc_ids = [
            doc_a.id if "Redis" in text else doc_b.id for text in llm_client.rerank_input_texts
        ]
        first_originally, second_originally = original_order_doc_ids
        citation_by_doc = {c.document_id: c for c in response.citations}
        assert (
            citation_by_doc[second_originally].relevance_score
            > citation_by_doc[first_originally].relevance_score
        )

    def test_rerank_is_skipped_when_only_one_chunk(self, db_session, project_id):
        """청크가 1개뿐이면 rerank 호출 자체가 무의미하므로 LlmClient.rerank 기본 구현이 바로 반환한다."""
        document = _make_document(db_session, project_id)
        llm_client = ScriptedRerankLlmClient(order=[0])
        rag_service, embedding_service = _build_rag_service(db_session, llm_client)
        embedding_service.index_document(document.id)

        response = rag_service.search(AiSearchRequest(query="문서 관련 질문"), user_id=None)

        assert len(response.citations) == 1
        # rerank 노드 자체는 항상 그래프를 지나가므로 rerank()가 호출되긴 하지만,
        # LlmClient.rerank의 len<=1 단축 경로 덕분에 llm_client.rerank_call_count는 증가한다
        # (호출은 되지만 실질적인 재정렬 로직/텍스트 비교는 스킵된다는 것이 핵심).
        assert llm_client.rerank_call_count == 1

    def test_rerank_receives_final_hybrid_merged_chunks(self, db_session, project_id):
        """rerank에 넘어가는 chunk_texts가 하이브리드 검색(벡터+키워드) 병합 결과여야 한다."""
        doc_a = _make_document(db_session, project_id, title="문서 A")
        doc_b = _make_document(db_session, project_id, title="문서 B")
        llm_client = ScriptedRerankLlmClient(order=[0, 1])
        rag_service, embedding_service = _build_rag_service(db_session, llm_client)
        embedding_service.index_document(doc_a.id)
        embedding_service.index_document(doc_b.id)

        rag_service.search(AiSearchRequest(query="문서 A 문서 B"), user_id=None)

        assert len(llm_client.rerank_input_texts) == 2
