"""
⑤ 멀티턴 대화 — 이전 턴(history)이 LLM에 전달되는지 검증한다.
① 스트리밍 — 그래프가 진행되는 노드 이름을 순서대로 내는지 검증한다.
"""

import pytest

from app.models.project import Project
from app.models.trouble_document import TroubleDocument
from app.schemas.ai import AiSearchRequest, ConversationMessage
from app.services.ai.embedding_provider import LocalHashEmbeddingProvider
from app.services.ai.embedding_service import EmbeddingService
from app.services.ai.llm_client import LlmClient, RagAnswer, TemplateLlmClient
from app.services.ai.prompt_builder import PromptBuilder
from app.services.ai.rag_service import RagService
from app.services.ai.retriever_service import RetrieverService
from app.services.ai.vector_store import FaissVectorStore
from tests.test_rag_reformulation import _settings


@pytest.fixture
def project_id(db_session):
    project = Project(name="멀티턴/스트리밍 테스트 프로젝트")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project.id


def _make_document(db_session, project_id) -> TroubleDocument:
    document = TroubleDocument(
        project_id=project_id,
        title="Redis 연결 문제",
        problem_description="Redis 연결이 끊긴다",
        solution="해결 방법: timeout 조정",
    )
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)
    return document


class RecordingMessagesLlmClient(LlmClient):
    """generate_structured()에 실제로 어떤 messages가 들어왔는지 기록해두는 테스트 더블."""

    def __init__(self):
        self.received_messages: list[dict] = []

    def generate(self, messages: list[dict[str, str]]) -> str:
        return '{"cause": "c", "similar_cases": "s", "solution": "sol"}'

    def generate_structured(self, messages: list[dict[str, str]]) -> RagAnswer:
        self.received_messages = messages
        return RagAnswer(cause="c", similar_cases="s", solution="sol")

    def classify(self, query: str) -> bool:
        return True

    def check_grounded(self, raw_response: str, context_json: str) -> bool:
        return True

    def condense_query(self, query: str, history: list[dict[str, str]]) -> str:
        return query  # 이 테스트는 history 전달 자체를 검증하므로 질문 압축은 하지 않는다.


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


class TestMultiTurn:
    def test_history_is_forwarded_to_llm_prompt(self, db_session, project_id):
        document = _make_document(db_session, project_id)
        llm_client = RecordingMessagesLlmClient()
        rag_service, embedding_service = _build_rag_service(db_session, llm_client)
        embedding_service.index_document(document.id)

        history = [
            ConversationMessage(role="user", content="Redis 연결이 왜 끊겨요?"),
            ConversationMessage(role="assistant", content="timeout 설정을 확인해보세요."),
        ]
        rag_service.search(
            AiSearchRequest(query="그럼 timeout은 몇 초로 하면 돼요?", history=history), user_id=None
        )

        contents = [m["content"] for m in llm_client.received_messages]
        assert "Redis 연결이 왜 끊겨요?" in contents
        assert "timeout 설정을 확인해보세요." in contents
        # 이전 대화가 시스템 프롬프트 뒤, 이번 질문 앞에 순서대로 들어가야 한다
        assert llm_client.received_messages[0]["role"] == "system"
        assert llm_client.received_messages[1]["content"] == "Redis 연결이 왜 끊겨요?"
        assert llm_client.received_messages[-1]["content"].startswith("질문: 그럼 timeout은")

    def test_empty_history_does_not_break_first_turn(self, db_session, project_id):
        document = _make_document(db_session, project_id)
        llm_client = RecordingMessagesLlmClient()
        rag_service, embedding_service = _build_rag_service(db_session, llm_client)
        embedding_service.index_document(document.id)

        response = rag_service.search(AiSearchRequest(query="Redis 연결 문제"), user_id=None)

        assert response.answer
        # system + user(질문) 두 개만 있어야 한다 (history가 비어있으므로)
        assert len(llm_client.received_messages) == 2


class TestStreaming:
    def test_stream_yields_expected_node_sequence_on_success(self, db_session, project_id):
        document = _make_document(db_session, project_id)
        rag_service, embedding_service = _build_rag_service(db_session, TemplateLlmClient())
        embedding_service.index_document(document.id)

        node_names = [
            node_name
            for node_name, _state in rag_service.stream(
                AiSearchRequest(query="Redis 연결이 끊기는 이유가 뭘까?"), user_id=None
            )
        ]

        # "token"은 generate 노드 실행 "도중"에 나오는 커스텀 이벤트라 별도로 걸러서 확인한다.
        structural_nodes = [n for n in node_names if n != "token"]
        assert structural_nodes == ["condense", "classify", "retrieve", "rerank", "generate", "validate"]
        assert "token" in node_names  # 답변이 부분적으로 채워지는 이벤트가 실제로 나왔는지

    def test_stream_yields_progressively_filled_partial_answers(self, db_session, project_id):
        """TemplateLlmClient의 stream_structured()가 흉내내는 점진적 채움이 실제로 커진다."""
        document = _make_document(db_session, project_id)
        rag_service, embedding_service = _build_rag_service(db_session, TemplateLlmClient())
        embedding_service.index_document(document.id)

        token_events = [
            state["partial_answer"]
            for node_name, state in rag_service.stream(
                AiSearchRequest(query="Redis 연결이 끊기는 이유가 뭘까?"), user_id=None
            )
            if node_name == "token"
        ]

        assert len(token_events) >= 2
        # 뒤로 갈수록 내용이 더 채워져야 한다 (완전히 같은 문자열이 반복되면 안 됨)
        assert token_events[0] != token_events[-1]
        assert len(token_events[-1]) >= len(token_events[0])

    def test_stream_yields_off_topic_path(self, db_session, project_id):
        rag_service, _ = _build_rag_service(db_session, TemplateLlmClient())

        node_names = [
            node_name
            for node_name, _state in rag_service.stream(AiSearchRequest(query="안녕하세요"), user_id=None)
        ]

        assert node_names == ["condense", "classify", "handle_off_topic"]

    def test_stream_final_state_contains_response(self, db_session, project_id):
        document = _make_document(db_session, project_id)
        rag_service, embedding_service = _build_rag_service(db_session, TemplateLlmClient())
        embedding_service.index_document(document.id)

        states = list(
            rag_service.stream(AiSearchRequest(query="Redis 연결이 끊기는 이유가 뭘까?"), user_id=None)
        )
        last_node, last_state = states[-1]

        assert last_node == "validate"
        assert "response" in last_state
        assert last_state["response"].citations
