"""
ChromaVectorStore 통합 테스트 (실제 chromadb PersistentClient 사용, 네트워크 불필요).

FaissVectorStore와 달리 디스크에 영속되므로, "프로세스가 재시작돼도 색인이
남아있는지"까지 검증한다 — 이게 FAISS 대비 Chroma를 쓰는 핵심 이유다.
"""
import pytest

from app.services.ai.embedding_provider import LocalHashEmbeddingProvider
from app.services.ai.vector_store import ChromaVectorStore


@pytest.fixture
def provider():
    return LocalHashEmbeddingProvider()


@pytest.fixture
def store(tmp_path, provider):
    from app.core.config import Settings

    settings = Settings(
        DATABASE_URL="sqlite:///:memory:",
        REDIS_URL="redis://localhost:6379/0",
        CELERY_BROKER_URL="redis://localhost:6379/1",
        CELERY_RESULT_BACKEND="redis://localhost:6379/2",
        JWT_SECRET_KEY="test-secret",
        CHROMA_PERSIST_DIR=str(tmp_path / "chroma_data"),
        CHROMA_COLLECTION_NAME="test_collection",
    )
    return ChromaVectorStore(dimension=provider.dimension, settings=settings)


class TestChromaVectorStore:
    def test_upsert_and_search_ranks_relevant_document_first(self, store, provider):
        texts = ["Redis 커넥션이 자꾸 끊기는 문제", "Kafka Consumer Lag 문제 해결"]
        vectors = provider.embed_texts(texts)
        store.upsert_batch([("doc1:0", vectors[0]), ("doc2:0", vectors[1])])

        query = provider.embed_texts(["Redis 연결이 끊기는 원인이 뭘까?"])[0]
        results = store.search(query, top_k=2)

        assert results[0].vector_id == "doc1:0"
        assert results[0].score > results[1].score

    def test_search_on_empty_collection_returns_empty(self, store, provider):
        query = provider.embed_texts(["아무 질문"])[0]
        assert store.search(query, top_k=5) == []

    def test_delete_removes_vector(self, store, provider):
        vectors = provider.embed_texts(["A", "B"])
        store.upsert_batch([("v1", vectors[0]), ("v2", vectors[1])])

        store.delete(["v1"])
        results = store.search(vectors[0], top_k=5)

        assert "v1" not in [r.vector_id for r in results]
        assert "v2" in [r.vector_id for r in results]

    def test_upsert_same_id_overwrites(self, store, provider):
        vectors = provider.embed_texts(["원본 텍스트", "다른 텍스트"])
        store.upsert_batch([("v1", vectors[0])])
        store.upsert_batch([("v1", vectors[1])])  # 같은 id로 재삽입 (재색인 시나리오)

        results = store.search(vectors[1], top_k=5)
        assert len(results) == 1
        assert results[0].vector_id == "v1"
        assert results[0].score > 0.99  # 자기 자신과의 유사도이므로 1에 가까워야 함

    def test_data_persists_across_new_store_instance(self, tmp_path, provider):
        """디스크 영속성 확인 — FAISS와 달리 새 인스턴스(프로세스 재시작 흉내)에서도 유지되어야 한다."""
        from app.core.config import Settings

        settings = Settings(
            DATABASE_URL="sqlite:///:memory:",
            REDIS_URL="redis://localhost:6379/0",
            CELERY_BROKER_URL="redis://localhost:6379/1",
            CELERY_RESULT_BACKEND="redis://localhost:6379/2",
            JWT_SECRET_KEY="test-secret",
            CHROMA_PERSIST_DIR=str(tmp_path / "chroma_persist"),
            CHROMA_COLLECTION_NAME="persist_test",
        )

        vector = provider.embed_texts(["영속성 테스트 문서"])[0]
        first_store = ChromaVectorStore(dimension=provider.dimension, settings=settings)
        first_store.upsert_batch([("doc1:0", vector)])

        # 완전히 새로운 인스턴스 — 프로세스가 재시작된 상황을 흉내낸다.
        second_store = ChromaVectorStore(dimension=provider.dimension, settings=settings)
        results = second_store.search(vector, top_k=1)

        assert len(results) == 1
        assert results[0].vector_id == "doc1:0"
