"""
① 질문 분류(classify) — 트러블슈팅과 무관한 질문은 검색 없이 안내 메시지로 끝난다.
③ 자체 검증(validate) — 답변이 CONTEXT에 근거하지 않았다고 판단되면 재검색을 시도한다.
"""
import pytest

from app.models.project import Project
from app.models.trouble_document import TroubleDocument
from app.schemas.ai import AiSearchRequest
from app.services.ai.embedding_provider import LocalHashEmbeddingProvider
from app.services.ai.embedding_service import EmbeddingService
from app.services.ai.llm_client import TemplateLlmClient
from app.services.ai.prompt_builder import PromptBuilder
from app.services.ai.rag_service import RagService
from app.services.ai.retriever_service import RetrieverService
from app.services.ai.vector_store import FaissVectorStore
from tests.test_rag_reformulation import CountingRetrieverService, ScriptedReformulateLlmClient, _settings


@pytest.fixture
def project_id(db_session):
    project = Project(name="분류/검증 테스트 프로젝트")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project.id


class TestClassifyNode:
    def test_greeting_is_classified_off_topic_and_skips_retrieval(self, db_session, project_id):
        provider = LocalHashEmbeddingProvider()
        vector_store = FaissVectorStore(dimension=provider.dimension)
        settings = _settings()
        embedding_service = EmbeddingService(db=db_session, provider=provider, vector_store=vector_store)
        retriever_service = CountingRetrieverService(
            db=db_session, provider=provider, vector_store=vector_store, settings=settings
        )
        rag_service = RagService(
            db=db_session,
            embedding_service=embedding_service,
            retriever_service=retriever_service,
            prompt_builder=PromptBuilder(),
            llm_client=TemplateLlmClient(),
            settings=settings,
        )

        response = rag_service.search(AiSearchRequest(query="안녕하세요"), user_id=None)

        assert response.on_topic is False
        assert retriever_service.call_count == 0  # 검색 자체가 실행되지 않아야 한다
        assert response.citations == []

    def test_troubleshooting_question_is_classified_on_topic(self, db_session, project_id):
        document = TroubleDocument(
            project_id=project_id,
            title="Redis 연결 문제",
            problem_description="Redis 연결이 끊긴다",
            solution="해결 방법: timeout 조정",
        )
        db_session.add(document)
        db_session.commit()
        db_session.refresh(document)

        provider = LocalHashEmbeddingProvider()
        vector_store = FaissVectorStore(dimension=provider.dimension)
        settings = _settings()
        embedding_service = EmbeddingService(db=db_session, provider=provider, vector_store=vector_store)
        embedding_service.index_document(document.id)
        retriever_service = RetrieverService(
            db=db_session, provider=provider, vector_store=vector_store, settings=settings
        )
        rag_service = RagService(
            db=db_session,
            embedding_service=embedding_service,
            retriever_service=retriever_service,
            prompt_builder=PromptBuilder(),
            llm_client=TemplateLlmClient(),
            settings=settings,
        )

        response = rag_service.search(
            AiSearchRequest(query="Redis 연결이 끊기는 이유가 뭘까?"), user_id=None
        )

        assert response.on_topic is True
        assert len(response.citations) == 1


class ScriptedGroundedLlmClient(ScriptedReformulateLlmClient):
    """check_grounded()의 반환값을 호출 순서대로 미리 정해둘 수 있는 테스트 더블."""

    def __init__(self, reformulated_queries, grounded_results):
        super().__init__(reformulated_queries)
        self._grounded_results = list(grounded_results)
        self.check_grounded_call_count = 0

    def check_grounded(self, raw_response: str, context_json: str) -> bool:
        idx = min(self.check_grounded_call_count, len(self._grounded_results) - 1)
        self.check_grounded_call_count += 1
        return self._grounded_results[idx]


def _make_document(db_session, project_id, **overrides) -> TroubleDocument:
    defaults = {
        "project_id": project_id,
        "title": "테스트 문서",
        "problem_description": "테스트 설명",
        "solution": "테스트 해결책",
    }
    defaults.update(overrides)
    document = TroubleDocument(**defaults)
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)
    return document


def _build_rag_service_with_client(db_session, llm_client, **settings_overrides):
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


class TestValidateNode:
    def test_grounded_answer_is_returned_as_is(self, db_session, project_id):
        document = _make_document(db_session, project_id)
        llm_client = ScriptedGroundedLlmClient(reformulated_queries=[], grounded_results=[True])
        rag_service, embedding_service = _build_rag_service_with_client(
            db_session, llm_client, RAG_MAX_RETRIEVAL_ATTEMPTS=1
        )
        embedding_service.index_document(document.id)

        response = rag_service.search(AiSearchRequest(query="테스트 문서 관련 질문"), user_id=None)

        assert response.is_grounded is True
        assert llm_client.reformulate_call_count == 0

    def test_ungrounded_answer_triggers_reformulate_retry(self, db_session, project_id):
        """1차 검증에서 근거 없다고 판단되면 재구성 후 재시도하고, 2차에서 통과하면 끝난다."""
        document = _make_document(db_session, project_id)
        llm_client = ScriptedGroundedLlmClient(
            reformulated_queries=["재구성된 질문"], grounded_results=[False, True]
        )
        rag_service, embedding_service = _build_rag_service_with_client(
            db_session, llm_client, RAG_MAX_RETRIEVAL_ATTEMPTS=1
        )
        embedding_service.index_document(document.id)

        response = rag_service.search(AiSearchRequest(query="테스트 문서 관련 질문"), user_id=None)

        assert response.is_grounded is True
        assert llm_client.reformulate_call_count == 1
        assert llm_client.check_grounded_call_count == 2

    def test_ungrounded_after_retry_budget_exhausted_returns_flagged_response(self, db_session, project_id):
        """재시도해도 계속 근거가 불확실하면, 포기하지 않고 is_grounded=False로 표시해 반환한다."""
        document = _make_document(db_session, project_id)
        llm_client = ScriptedGroundedLlmClient(
            reformulated_queries=["재구성된 질문"], grounded_results=[False, False]
        )
        rag_service, embedding_service = _build_rag_service_with_client(
            db_session, llm_client, RAG_MAX_RETRIEVAL_ATTEMPTS=1
        )
        embedding_service.index_document(document.id)

        response = rag_service.search(AiSearchRequest(query="테스트 문서 관련 질문"), user_id=None)

        assert response.is_grounded is False
        assert response.answer  # 그래도 답변 자체는 반환되어야 한다 (빈 응답이 아님)
