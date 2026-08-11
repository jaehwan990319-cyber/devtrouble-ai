"""
LangGraph 재검색 루프(retrieve → reformulate → retrieve) 통합 테스트.

검색 결과가 빈약할 때 질문을 재구성해 재시도하고, 그래도 안 되면
정해진 횟수(settings.RAG_MAX_RETRIEVAL_ATTEMPTS) 안에서 멈추는지 확인한다.
TemplateLlmClient의 실제 휴리스틱 품질에 기대지 않도록, 재구성 결과를
완전히 통제할 수 있는 Fake LlmClient로 그래프의 "기계적 동작"만 검증한다.
"""
import pytest

from app.core.config import Settings
from app.models.project import Project
from app.models.trouble_document import TroubleDocument
from app.schemas.ai import AiSearchRequest
from app.services.ai.embedding_provider import LocalHashEmbeddingProvider
from app.services.ai.embedding_service import EmbeddingService
from app.services.ai.llm_client import LlmClient, RagAnswer
from app.services.ai.prompt_builder import PromptBuilder
from app.services.ai.rag_service import RagService
from app.services.ai.retriever_service import RetrieverService
from app.services.ai.vector_store import FaissVectorStore


class CountingRetrieverService(RetrieverService):
    """retrieve가 몇 번 호출됐는지 세기 위한 스파이."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.call_count = 0

    def search(self, query_embedding, top_k=None):
        self.call_count += 1
        return super().search(query_embedding, top_k)


class ScriptedReformulateLlmClient(LlmClient):
    """
    reformulate() 호출 시마다 미리 정해둔 질문을 순서대로 돌려주는 테스트 더블.
    generate()는 항상 같은 형식의 JSON을 반환한다 (파싱 검증에는 관심 없음).
    """

    def __init__(self, reformulated_queries: list[str]):
        self._reformulated_queries = list(reformulated_queries)
        self.reformulate_call_count = 0

    def generate(self, messages: list[dict[str, str]]) -> str:
        return '{"cause": "테스트 원인", "similar_cases": "", "solution": "테스트 해결책"}'

    def generate_structured(self, messages: list[dict[str, str]]) -> RagAnswer:
        return RagAnswer(cause="테스트 원인", similar_cases="", solution="테스트 해결책")

    def reformulate(self, query: str) -> str:
        idx = min(self.reformulate_call_count, len(self._reformulated_queries) - 1)
        self.reformulate_call_count += 1
        return self._reformulated_queries[idx]

    def classify(self, query: str) -> bool:
        return True  # 이 테스트 파일은 재검색 루프만 검증하므로 항상 on-topic으로 취급한다.

    def check_grounded(self, raw_response: str, context_json: str) -> bool:
        return True  # self-critique는 별도 관심사이므로 여기서는 항상 통과시킨다.


def _settings(**overrides) -> Settings:
    defaults = {
        "DATABASE_URL": "sqlite:///:memory:",
        "REDIS_URL": "redis://localhost:6379/0",
        "CELERY_BROKER_URL": "redis://localhost:6379/1",
        "CELERY_RESULT_BACKEND": "redis://localhost:6379/2",
        "JWT_SECRET_KEY": "test-secret",
    }
    defaults.update(overrides)
    return Settings(**defaults)


@pytest.fixture
def project_id(db_session):
    project = Project(name="재검색 테스트 프로젝트")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project.id


def _make_document(db_session, project_id, **overrides) -> TroubleDocument:
    defaults = {
        "project_id": project_id,
        "title": "완전히 특수한 고유토큰 자이로스코프987 장애",
        "problem_description": "자이로스코프987 센서 드라이버가 부팅 시 초기화되지 않는다.",
        "solution": "해결 방법: 드라이버 로드 순서를 커널 모듈보다 뒤로 옮겼다.",
    }
    defaults.update(overrides)
    document = TroubleDocument(**defaults)
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)
    return document


def _build_rag_service(db_session, llm_client) -> tuple[RagService, CountingRetrieverService]:
    provider = LocalHashEmbeddingProvider()
    vector_store = FaissVectorStore(dimension=provider.dimension)
    settings = _settings(RAG_MAX_RETRIEVAL_ATTEMPTS=1, RAG_RETRY_SCORE_THRESHOLD=0.05)

    embedding_service = EmbeddingService(db=db_session, provider=provider, vector_store=vector_store)
    retriever_service = CountingRetrieverService(
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
    return rag_service, retriever_service, embedding_service


class TestReformulationLoop:
    def test_reformulated_query_finds_document_original_missed(self, db_session, project_id):
        """
        원래 질문으로는 못 찾지만(관련성 낮음), 재구성된 질문으로는 정확히 찾는 시나리오.
        LocalHash 임베딩은 완전히 다른 단어 집합이면 유사도가 거의 0에 가까우므로,
        엉뚱한 원본 질문 → 문서 고유 키워드로 재구성된 질문 순으로 스크립트를 짠다.
        """
        document = _make_document(db_session, project_id)
        llm_client = ScriptedReformulateLlmClient(
            reformulated_queries=["자이로스코프987 드라이버 초기화 장애"]
        )
        rag_service, retriever_service, embedding_service = _build_rag_service(db_session, llm_client)
        embedding_service.index_document(document.id)

        response = rag_service.search(
            AiSearchRequest(query="오늘 점심 메뉴는 뭘로 정할지 고민이다"), user_id=None
        )

        assert len(response.citations) == 1
        assert response.citations[0].document_id == document.id
        assert retriever_service.call_count == 2  # 원본 1회 + 재구성 후 1회
        assert llm_client.reformulate_call_count == 1

    def test_gives_up_gracefully_after_max_attempts(self, db_session, project_id):
        """재구성해도 계속 못 찾으면, 정해진 횟수만 시도하고 안내 메시지로 끝나야 한다."""
        llm_client = ScriptedReformulateLlmClient(
            reformulated_queries=["그래도 여전히 무관한 질문"]
        )
        rag_service, retriever_service, _ = _build_rag_service(db_session, llm_client)
        # 문서를 하나도 색인하지 않아 인덱스가 완전히 비어있는 상태.

        response = rag_service.search(AiSearchRequest(query="아무 문서도 없는 질문"), user_id=None)

        assert response.citations == []
        assert "찾지 못했습니다" in response.answer
        # RAG_MAX_RETRIEVAL_ATTEMPTS=1 이므로 원본 1회 + 재시도 1회 = 최대 2회에서 멈춰야 한다.
        assert retriever_service.call_count == 2
        assert llm_client.reformulate_call_count == 1

    def test_first_attempt_success_never_triggers_reformulate(self, db_session, project_id):
        """처음부터 잘 찾으면 reformulate는 아예 호출되지 않아야 한다 (불필요한 재시도 방지)."""
        document = _make_document(db_session, project_id)
        llm_client = ScriptedReformulateLlmClient(reformulated_queries=["호출되면 안 됨"])
        rag_service, retriever_service, embedding_service = _build_rag_service(db_session, llm_client)
        embedding_service.index_document(document.id)

        response = rag_service.search(
            AiSearchRequest(query="자이로스코프987 장애 초기화 드라이버"), user_id=None
        )

        assert len(response.citations) == 1
        assert retriever_service.call_count == 1
        assert llm_client.reformulate_call_count == 0

    def test_audit_log_records_original_query_not_reformulated(self, db_session, project_id):
        """감사 로그에는 재구성된 질문이 아니라 사용자가 실제로 입력한 원문이 남아야 한다."""
        from app.models.ai_query_log import AiQueryLog

        document = _make_document(db_session, project_id)
        llm_client = ScriptedReformulateLlmClient(
            reformulated_queries=["자이로스코프987 드라이버 초기화 장애"]
        )
        rag_service, _, embedding_service = _build_rag_service(db_session, llm_client)
        embedding_service.index_document(document.id)

        original_query = "오늘 점심 메뉴는 뭘로 정할지 고민이다"
        rag_service.search(AiSearchRequest(query=original_query), user_id=None)

        logs = db_session.query(AiQueryLog).all()
        assert len(logs) == 1
        assert logs[0].query_text == original_query

    def test_zero_max_attempts_disables_retry(self, db_session, project_id):
        """RAG_MAX_RETRIEVAL_ATTEMPTS=0이면 재시도 없이 첫 시도 결과로 바로 끝나야 한다."""
        llm_client = ScriptedReformulateLlmClient(reformulated_queries=["호출 안 됨"])
        provider = LocalHashEmbeddingProvider()
        vector_store = FaissVectorStore(dimension=provider.dimension)
        settings = _settings(RAG_MAX_RETRIEVAL_ATTEMPTS=0, RAG_RETRY_SCORE_THRESHOLD=0.05)

        embedding_service = EmbeddingService(db=db_session, provider=provider, vector_store=vector_store)
        retriever_service = CountingRetrieverService(
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

        response = rag_service.search(AiSearchRequest(query="빈 인덱스 질문"), user_id=None)

        assert "찾지 못했습니다" in response.answer
        assert retriever_service.call_count == 1
        assert llm_client.reformulate_call_count == 0
