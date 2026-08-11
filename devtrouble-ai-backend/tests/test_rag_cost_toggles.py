"""
④ 비용 절감 — RAG_ENABLE_CLASSIFY / RAG_ENABLE_RERANK / RAG_ENABLE_VALIDATION 토글이
각 단계의 LLM 호출을 실제로 건너뛰는지 검증한다. 그래프 구조(노드 시퀀스) 자체는
그대로 유지하고, 각 노드 "내부"에서 LLM 호출만 생략되는 방식이다.
"""
import pytest

from app.models.project import Project
from app.models.trouble_document import TroubleDocument
from app.schemas.ai import AiSearchRequest
from app.services.ai.embedding_provider import LocalHashEmbeddingProvider
from app.services.ai.embedding_service import EmbeddingService
from app.services.ai.prompt_builder import PromptBuilder
from app.services.ai.rag_service import RagService
from app.services.ai.retriever_service import RetrieverService
from app.services.ai.vector_store import FaissVectorStore
from tests.test_rag_classify_validate import ScriptedGroundedLlmClient
from tests.test_rag_reformulation import _settings
from tests.test_rag_rerank import ScriptedRerankLlmClient


@pytest.fixture
def project_id(db_session):
    project = Project(name="비용절감 테스트 프로젝트")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project.id


def _make_document(db_session, project_id, **overrides) -> TroubleDocument:
    defaults = {"project_id": project_id, "title": "테스트 문서", "problem_description": "설명"}
    defaults.update(overrides)
    document = TroubleDocument(**defaults)
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)
    return document


def _build_rag_service(db_session, llm_client, **settings_overrides):
    provider = LocalHashEmbeddingProvider()
    vector_store = FaissVectorStore(dimension=provider.dimension)
    settings = _settings(**settings_overrides)
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


class TestCostToggles:
    def test_classify_disabled_skips_llm_call_and_treats_as_on_topic(self, db_session, project_id):
        document = _make_document(db_session, project_id)
        llm_client = ScriptedGroundedLlmClient(
            reformulated_queries=["아무 질문"], grounded_results=[True]
        )
        rag_service, embedding_service = _build_rag_service(
            db_session, llm_client, RAG_ENABLE_CLASSIFY=False
        )
        embedding_service.index_document(document.id)

        # classify()가 호출되면 예외가 나도록 만들어서, 호출 여부를 확실히 검증한다.
        def _boom(query):
            raise AssertionError("classify()가 호출되면 안 됩니다 (RAG_ENABLE_CLASSIFY=False)")

        llm_client.classify = _boom

        response = rag_service.search(AiSearchRequest(query="아무 질문"), user_id=None)

        assert response.on_topic is True

    def test_rerank_disabled_skips_llm_call_and_keeps_original_order(self, db_session, project_id):
        doc_a = _make_document(db_session, project_id, title="문서 A")
        doc_b = _make_document(db_session, project_id, title="문서 B")
        llm_client = ScriptedRerankLlmClient(order=[1, 0])
        rag_service, embedding_service = _build_rag_service(
            db_session, llm_client, RAG_ENABLE_RERANK=False
        )
        embedding_service.index_document(doc_a.id)
        embedding_service.index_document(doc_b.id)

        rag_service.search(AiSearchRequest(query="문서 A 문서 B"), user_id=None)

        assert llm_client.rerank_call_count == 0

    def test_validation_disabled_skips_llm_call_and_always_grounded(self, db_session, project_id):
        document = _make_document(db_session, project_id)
        llm_client = ScriptedGroundedLlmClient(reformulated_queries=[], grounded_results=[False])
        rag_service, embedding_service = _build_rag_service(
            db_session, llm_client, RAG_ENABLE_VALIDATION=False
        )
        embedding_service.index_document(document.id)

        response = rag_service.search(AiSearchRequest(query="테스트 문서 관련 질문"), user_id=None)

        # check_grounded가 False를 반환하도록 스크립트해뒀지만, 검증 자체가 꺼져 있으므로
        # 호출되지 않고 항상 grounded=True로 취급되어야 한다.
        assert response.is_grounded is True
        assert llm_client.check_grounded_call_count == 0

    def test_all_toggles_off_still_produces_valid_response(self, db_session, project_id):
        """세 토글을 전부 꺼도 파이프라인 자체는 정상적으로 끝까지 돌아야 한다."""
        document = _make_document(db_session, project_id)
        llm_client = ScriptedGroundedLlmClient(reformulated_queries=[], grounded_results=[True])
        rag_service, embedding_service = _build_rag_service(
            db_session,
            llm_client,
            RAG_ENABLE_CLASSIFY=False,
            RAG_ENABLE_RERANK=False,
            RAG_ENABLE_VALIDATION=False,
        )
        embedding_service.index_document(document.id)

        response = rag_service.search(AiSearchRequest(query="테스트 문서 관련 질문"), user_id=None)

        assert response.answer
        assert len(response.citations) == 1
        assert response.on_topic is True
        assert response.is_grounded is True
