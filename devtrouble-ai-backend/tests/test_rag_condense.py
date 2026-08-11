"""
① 질문 압축(query condensation) — 후속 질문이 검색에도 반영되는지 검증한다.

이전 구조의 한계: history는 generate 프롬프트에만 반영되고 retrieve는 항상
이번 질문 그대로 검색해서, "그럼 그건요?" 같은 후속 질문은 검색에 실패하기 쉬웠다.
condense 노드가 이 문제를 해결하는지, Fake LlmClient로 완전히 통제해 검증한다.
"""
import pytest

from app.models.project import Project
from app.models.trouble_document import TroubleDocument
from app.schemas.ai import AiSearchRequest, ConversationMessage
from app.services.ai.embedding_provider import LocalHashEmbeddingProvider
from app.services.ai.embedding_service import EmbeddingService
from app.services.ai.llm_client import TemplateLlmClient
from app.services.ai.prompt_builder import PromptBuilder
from app.services.ai.rag_service import RagService
from app.services.ai.retriever_service import RetrieverService
from app.services.ai.vector_store import FaissVectorStore
from tests.test_rag_multiturn_streaming import RecordingMessagesLlmClient
from tests.test_rag_reformulation import _settings


@pytest.fixture
def project_id(db_session):
    project = Project(name="질문압축 테스트 프로젝트")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project.id


class ScriptedCondenseLlmClient(RecordingMessagesLlmClient):
    """condense_query()가 항상 미리 정해둔 문자열을 반환하는 테스트 더블."""

    def __init__(self, condensed_query: str):
        super().__init__()
        self._condensed_query = condensed_query
        self.condense_call_count = 0
        self.condense_received_query: str | None = None
        self.condense_received_history: list[dict] | None = None

    def condense_query(self, query: str, history: list[dict[str, str]]) -> str:
        self.condense_call_count += 1
        self.condense_received_query = query
        self.condense_received_history = history
        return self._condensed_query


def _make_document(db_session, project_id, **overrides) -> TroubleDocument:
    defaults = {
        "project_id": project_id,
        "title": "자이로스코프987 드라이버 초기화 장애",
        "problem_description": "자이로스코프987 센서 드라이버가 부팅 시 초기화되지 않는다.",
        "solution": "해결 방법: 드라이버 로드 순서를 커널 모듈보다 뒤로 옮겼다.",
    }
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


class TestQueryCondensation:
    def test_condensed_query_is_used_for_retrieval(self, db_session, project_id):
        """압축된 질문이 검색에도 그대로 쓰여서, 원래 질문으로는 못 찾을 문서를 찾아야 한다."""
        document = _make_document(db_session, project_id)
        llm_client = ScriptedCondenseLlmClient(condensed_query="자이로스코프987 드라이버 초기화 장애")
        rag_service, embedding_service = _build_rag_service(db_session, llm_client)
        embedding_service.index_document(document.id)

        history = [
            ConversationMessage(role="user", content="자이로스코프987 문제 있었잖아요"),
            ConversationMessage(role="assistant", content="네, 초기화 문제였죠."),
        ]
        response = rag_service.search(
            AiSearchRequest(query="그거 어떻게 고쳤어요?", history=history), user_id=None
        )

        assert llm_client.condense_call_count == 1
        assert llm_client.condense_received_query == "그거 어떻게 고쳤어요?"
        assert len(response.citations) == 1
        assert response.citations[0].document_id == document.id

    def test_no_history_skips_condensation_entirely(self, db_session, project_id):
        """첫 질문(history 없음)이면 condense_query() 자체를 호출하지 않아야 한다 (비용 절감)."""
        document = _make_document(db_session, project_id)
        llm_client = ScriptedCondenseLlmClient(condensed_query="호출되면 안 됨")
        rag_service, embedding_service = _build_rag_service(db_session, llm_client)
        embedding_service.index_document(document.id)

        rag_service.search(AiSearchRequest(query="자이로스코프987 드라이버 초기화 장애"), user_id=None)

        assert llm_client.condense_call_count == 0

    def test_condensation_disabled_via_setting(self, db_session, project_id):
        """RAG_ENABLE_QUERY_CONDENSATION=False면 history가 있어도 압축을 건너뛰어야 한다."""
        document = _make_document(db_session, project_id)
        llm_client = ScriptedCondenseLlmClient(condensed_query="호출되면 안 됨")
        rag_service, embedding_service = _build_rag_service(
            db_session, llm_client, RAG_ENABLE_QUERY_CONDENSATION=False
        )
        embedding_service.index_document(document.id)

        history = [ConversationMessage(role="user", content="이전 질문")]
        rag_service.search(AiSearchRequest(query="후속 질문", history=history), user_id=None)

        assert llm_client.condense_call_count == 0

    def test_template_client_condense_heuristic_prepends_last_user_turn(self):
        """TemplateLlmClient의 휴리스틱 — 직전 사용자 발화를 이번 질문 앞에 붙인다."""
        client = TemplateLlmClient()
        history = [
            {"role": "user", "content": "Redis 커넥션 문제"},
            {"role": "assistant", "content": "timeout을 확인하세요"},
        ]

        result = client.condense_query("몇 초로 하면 될까요?", history)

        assert result == "Redis 커넥션 문제 몇 초로 하면 될까요?"

    def test_template_client_condense_without_history_returns_query_unchanged(self):
        client = TemplateLlmClient()
        assert client.condense_query("첫 질문", []) == "첫 질문"
