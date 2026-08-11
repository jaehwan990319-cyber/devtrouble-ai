"""
RAG 파이프라인 통합 테스트.

OPENAI_API_KEY 없이도(로컬/CI 환경) 전체 파이프라인이 의미 있게 동작하는지
LocalHashEmbeddingProvider + FaissVectorStore + TemplateLlmClient 조합으로 검증한다.
운영 경로(OpenAiEmbeddingProvider/OpenAiLlmClient/QdrantVectorStore)는
langchain_openai/qdrant-client 호출부만 동일한 인터페이스로 교체되는 구조이므로
여기서 검증한 오케스트레이션 로직이 그대로 재사용된다.
"""
import json

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
from app.services.document_indexer import DocumentIndexer


class SpyDocumentIndexer(DocumentIndexer):
    """Celery를 실제로 거치지 않고 DocumentService가 인덱서를 호출했는지만 기록한다."""

    def __init__(self):
        self.indexed_ids: list[str] = []
        self.removed_ids: list[str] = []

    def index_document(self, document_id: str) -> None:
        self.indexed_ids.append(document_id)

    def remove_document(self, document_id: str) -> None:
        self.removed_ids.append(document_id)


@pytest.fixture
def rag_stack(db_session):
    """LocalHashEmbeddingProvider + FaissVectorStore를 공유하는 RAG 컴포넌트 세트."""
    provider = LocalHashEmbeddingProvider()
    vector_store = FaissVectorStore(dimension=provider.dimension)

    embedding_service = EmbeddingService(db=db_session, provider=provider, vector_store=vector_store)
    retriever_service = RetrieverService(db=db_session, provider=provider, vector_store=vector_store)
    rag_service = RagService(
        db=db_session,
        embedding_service=embedding_service,
        retriever_service=retriever_service,
        prompt_builder=PromptBuilder(),
        llm_client=TemplateLlmClient(),
    )
    return {
        "provider": provider,
        "vector_store": vector_store,
        "embedding_service": embedding_service,
        "retriever_service": retriever_service,
        "rag_service": rag_service,
    }


def _make_document(db_session, project_id, **overrides) -> TroubleDocument:
    defaults = {
        "project_id": project_id,
        "title": "Redis 커넥션 끊김 현상 해결",
        "problem_description": "운영 환경에서 Redis 커넥션이 주기적으로 끊기는 현상이 발생했다.",
        "error_message": "ConnectionResetError: Redis connection closed by peer",
        "solution": "해결 방법: Redis timeout 설정을 늘리고 커넥션 풀의 idle 타임아웃을 조정했다.",
    }
    defaults.update(overrides)
    document = TroubleDocument(**defaults)
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)
    return document


@pytest.fixture
def project_id(db_session):
    project = Project(name="테스트 프로젝트")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project.id


class TestChunking:
    def test_short_text_becomes_single_chunk(self, db_session):
        service = EmbeddingService(
            db=db_session, provider=LocalHashEmbeddingProvider(), vector_store=FaissVectorStore(384)
        )
        chunks = service.chunk_document("짧은 문단 하나.")
        assert chunks == ["짧은 문단 하나."]

    def test_paragraphs_are_packed_under_max_chars(self, db_session):
        service = EmbeddingService(
            db=db_session, provider=LocalHashEmbeddingProvider(), vector_store=FaissVectorStore(384)
        )
        text = "\n\n".join([f"문단 {i} " + ("내용 " * 10) for i in range(5)])

        chunks = service.chunk_document(text, max_chars=100, overlap=10)

        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 100 + 5  # 문단 결합 시 개행 여유 약간 허용

    def test_long_single_paragraph_is_hard_split_with_overlap(self, db_session):
        service = EmbeddingService(
            db=db_session, provider=LocalHashEmbeddingProvider(), vector_store=FaissVectorStore(384)
        )
        text = "가" * 250

        chunks = service.chunk_document(text, max_chars=100, overlap=20)

        assert len(chunks) == 4  # (250 - 100) / 80 올림 + 1
        assert all(len(c) <= 100 for c in chunks)
        # overlap 검증: 인접 청크의 끝/시작이 겹쳐야 한다
        assert chunks[0][-20:] == chunks[1][:20]

    def test_empty_text_produces_no_chunks(self, db_session):
        service = EmbeddingService(
            db=db_session, provider=LocalHashEmbeddingProvider(), vector_store=FaissVectorStore(384)
        )
        assert service.chunk_document("   \n\n   ") == []


class TestIndexing:
    def test_index_document_creates_embeddings_and_vectors(self, db_session, rag_stack, project_id):
        document = _make_document(db_session, project_id)

        rag_stack["embedding_service"].index_document(document.id)

        stored = rag_stack["embedding_service"].embedding_repo.list_by_document(document.id)
        assert len(stored) >= 1
        assert all(e.embedding_model == "local-hash-v1" for e in stored)
        assert rag_stack["vector_store"]._index.ntotal == len(stored)

    def test_reindexing_replaces_old_chunks(self, db_session, rag_stack, project_id):
        document = _make_document(db_session, project_id)
        rag_stack["embedding_service"].index_document(document.id)
        first_count = rag_stack["vector_store"]._index.ntotal

        document.title = "완전히 다른 제목으로 변경"
        db_session.commit()
        rag_stack["embedding_service"].index_document(document.id)

        stored = rag_stack["embedding_service"].embedding_repo.list_by_document(document.id)
        # 재색인 후에도 벡터 개수가 중복 누적되지 않아야 한다
        assert rag_stack["vector_store"]._index.ntotal == len(stored)
        assert first_count == len(stored)  # 이 테스트 문서는 청크 수가 동일하게 유지됨

    def test_remove_document_cleans_up_embeddings_and_vectors(self, db_session, rag_stack, project_id):
        document = _make_document(db_session, project_id)
        rag_stack["embedding_service"].index_document(document.id)
        assert rag_stack["vector_store"]._index.ntotal > 0

        rag_stack["embedding_service"].remove_document(document.id)

        assert rag_stack["embedding_service"].embedding_repo.list_by_document(document.id) == []
        assert rag_stack["vector_store"]._index.ntotal == 0

    def test_index_deleted_document_is_noop(self, db_session, rag_stack, project_id):
        from app.utils.datetime_utils import naive_utcnow

        document = _make_document(db_session, project_id)
        document.deleted_at = naive_utcnow()
        db_session.commit()

        rag_stack["embedding_service"].index_document(document.id)

        assert rag_stack["vector_store"]._index.ntotal == 0


class TestRetrieval:
    def test_search_ranks_relevant_document_first(self, db_session, rag_stack, project_id):
        redis_doc = _make_document(
            db_session, project_id,
            title="Redis 커넥션 끊김 현상",
            problem_description="Redis 연결이 자꾸 끊기는 문제가 있다.",
        )
        kafka_doc = _make_document(
            db_session, project_id,
            title="Kafka Consumer Lag 문제",
            problem_description="Kafka Consumer의 처리 지연이 계속 쌓인다.",
        )
        rag_stack["embedding_service"].index_document(redis_doc.id)
        rag_stack["embedding_service"].index_document(kafka_doc.id)

        query_embedding = rag_stack["provider"].embed_texts(["Redis 연결이 끊기는 원인이 뭘까?"])[0]
        results = rag_stack["retriever_service"].search(query_embedding, top_k=5)

        assert results[0].document_id == redis_doc.id

    def test_search_returns_empty_when_index_is_empty(self, db_session, rag_stack):
        query_embedding = rag_stack["provider"].embed_texts(["아무 질문"])[0]
        results = rag_stack["retriever_service"].search(query_embedding, top_k=5)
        assert results == []


class TestRagServiceEndToEnd:
    def test_search_returns_structured_answer_with_citation(self, db_session, rag_stack, project_id):
        document = _make_document(db_session, project_id)
        rag_stack["embedding_service"].index_document(document.id)

        response = rag_stack["rag_service"].search(
            AiSearchRequest(query="Redis 커넥션이 끊기는 이유가 뭐야?"), user_id=None
        )

        assert response.answer
        assert len(response.citations) == 1
        assert response.citations[0].document_id == document.id
        assert response.citations[0].title == document.title

    def test_search_with_no_indexed_documents_returns_graceful_message(self, db_session, rag_stack):
        response = rag_stack["rag_service"].search(
            AiSearchRequest(query="아무 문서도 없는 상태에서의 질문"), user_id=None
        )

        assert response.citations == []
        assert "찾지 못했습니다" in response.answer

    def test_search_scoped_by_project_id_excludes_other_projects(self, db_session, rag_stack, project_id):
        other_project = Project(name="다른 프로젝트")
        db_session.add(other_project)
        db_session.commit()
        db_session.refresh(other_project)

        target = _make_document(db_session, project_id, title="타겟 프로젝트 문서")
        other = _make_document(db_session, other_project.id, title="다른 프로젝트 문서")
        rag_stack["embedding_service"].index_document(target.id)
        rag_stack["embedding_service"].index_document(other.id)

        response = rag_stack["rag_service"].search(
            AiSearchRequest(query="Redis 커넥션 문제", project_id=project_id), user_id=None
        )

        cited_ids = {c.document_id for c in response.citations}
        assert cited_ids == {target.id}

    def test_query_is_logged_for_audit(self, db_session, rag_stack, project_id):
        from app.models.ai_query_log import AiQueryLog

        document = _make_document(db_session, project_id)
        rag_stack["embedding_service"].index_document(document.id)

        rag_stack["rag_service"].search(AiSearchRequest(query="감사 로그 확인용 질문"), user_id=None)

        logs = db_session.query(AiQueryLog).all()
        assert len(logs) == 1
        assert logs[0].query_text == "감사 로그 확인용 질문"


class TestDocumentServiceTriggersIndexer:
    """DocumentService가 CRUD 이후 DocumentIndexer를 올바른 시점에 호출하는지 검증한다.

    (실제 Celery는 사용하지 않고 Spy로 대체)
    """

    def test_create_document_triggers_index(self, client, db_session, project_id):
        from app.services.document_service import DocumentService

        indexer = SpyDocumentIndexer()
        service = DocumentService(db_session, indexer=indexer)

        document = service.create_document(
            project_id=project_id,
            author_id="author-1",
            title="테스트",
            problem_description="설명",
        )

        assert indexer.indexed_ids == [document.id]

    def test_update_document_triggers_reindex(self, db_session, project_id):
        from app.services.document_service import DocumentService

        indexer = SpyDocumentIndexer()
        service = DocumentService(db_session, indexer=indexer)
        document = service.create_document(
            project_id=project_id, author_id="author-1", title="원본", problem_description="설명"
        )
        indexer.indexed_ids.clear()

        service.update_document(document.id, "author-1", title="수정됨")

        assert indexer.indexed_ids == [document.id]

    def test_delete_document_triggers_removal(self, db_session, project_id):
        from app.services.document_service import DocumentService

        indexer = SpyDocumentIndexer()
        service = DocumentService(db_session, indexer=indexer)
        document = service.create_document(
            project_id=project_id, author_id="author-1", title="원본", problem_description="설명"
        )

        service.delete_document(document.id, "author-1")

        assert indexer.removed_ids == [document.id]


class TestAiSearchApiEndpoint:
    """API 엔드투엔드: 문서를 만들고 동기적으로 색인한 뒤 /api/v1/ai/search를 호출한다."""

    def test_ai_search_endpoint_returns_citation(self, client, db_session, project_id):
        client.post(
            "/api/v1/auth/signup",
            json={"email": "rag@example.com", "password": "password123", "nickname": "rag"},
        )
        tokens = client.post(
            "/api/v1/auth/login", json={"email": "rag@example.com", "password": "password123"}
        ).json()["data"]
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        create_response = client.post(
            "/api/v1/documents",
            json={
                "project_id": project_id,
                "title": "Redis 커넥션 끊김 현상 해결",
                "problem_description": "운영 환경에서 Redis 커넥션이 주기적으로 끊긴다.",
                "solution": "해결 방법: timeout 설정을 늘렸다.",
            },
            headers=headers,
        )
        document_id = create_response.json()["data"]["id"]

        # CeleryDocumentIndexer는 브로커가 없는 테스트 환경에서 큐잉에 실패하고
        # (예외를 흡수하고 로깅만 함) 조용히 넘어가므로, 실제 워커가 하는 일을
        # 여기서 동기적으로 대신 수행해 색인 결과를 만든다.
        from app.services.ai.embedding_service import EmbeddingService

        EmbeddingService(db=db_session).index_document(document_id)

        response = client.post("/api/v1/ai/search", json={"query": "Redis 연결이 끊기는 이유가 뭘까?"})

        assert response.status_code == 200
        body = response.json()["data"]
        assert len(body["citations"]) == 1
        assert body["citations"][0]["document_id"] == document_id

    def test_ai_search_stream_endpoint_yields_sse_events(self, client):
        """스트리밍 엔드포인트가 SSE 형식으로 단계별 이벤트 + 최종 응답을 순서대로 보내는지 확인한다."""
        with client.stream(
            "POST", "/api/v1/ai/search/stream", json={"query": "아무 문서도 없는 상태에서의 질문"}
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")

            events = []
            for line in response.iter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line.removeprefix("data: ")))

        stages = [e["stage"] for e in events]
        assert stages[0] == "condense"
        assert stages[-1] == "done"
        assert events[-1]["response"]["citations"] == []

    def test_ai_search_stream_endpoint_yields_token_events_with_answer(self, client, db_session, project_id):
        """실제로 찾아지는 질문이면 generate 도중 'token' 이벤트로 답변이 점점 채워져 와야 한다."""
        from app.models.trouble_document import TroubleDocument
        from app.services.ai.embedding_service import EmbeddingService

        document = TroubleDocument(
            project_id=project_id,
            title="Redis 커넥션 끊김 현상 해결",
            problem_description="운영 환경에서 Redis 커넥션이 주기적으로 끊긴다.",
            solution="해결 방법: timeout 설정을 늘렸다.",
        )
        db_session.add(document)
        db_session.commit()
        db_session.refresh(document)
        EmbeddingService(db=db_session).index_document(document.id)

        with client.stream(
            "POST", "/api/v1/ai/search/stream", json={"query": "Redis 연결이 끊기는 이유가 뭘까?"}
        ) as response:
            events = [
                json.loads(line.removeprefix("data: "))
                for line in response.iter_lines()
                if line.startswith("data: ")
            ]

        token_events = [e for e in events if e["stage"] == "token"]
        assert len(token_events) >= 1
        assert all("answer" in e for e in token_events)
        assert events[-1]["stage"] == "done"
        assert events[-1]["response"]["citations"]
