"""
RAG 파이프라인 2단계: Vector Search로 Top-K 문서 검색.

PRD AI 파이프라인 대응: ... → Vector Search → [Top K 문서 검색] → Prompt 생성 → ...

VectorStore는 (vector_id, score)만 알고 있으므로, 여기서 document_embeddings
테이블을 조회해 실제 청크 원문/문서 ID로 역참조한다 (RDB가 Source of Truth).
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.repositories.embedding_repository import EmbeddingRepository
from app.services.ai.embedding_provider import EmbeddingProvider, get_embedding_provider
from app.services.ai.vector_store import VectorStore, get_vector_store


@dataclass
class RetrievedChunk:
    document_id: str
    chunk_text: str
    relevance_score: float


class RetrieverService:
    def __init__(
        self,
        db: Session,
        provider: EmbeddingProvider | None = None,
        vector_store: VectorStore | None = None,
        settings: Settings | None = None,
    ):
        self.db = db
        self.settings = settings or get_settings()
        self.provider = provider or get_embedding_provider(self.settings)
        self.vector_store = vector_store or get_vector_store(self.provider.dimension, self.settings)
        self.embedding_repo = EmbeddingRepository(db)

    def search(self, query_embedding: list[float], top_k: int | None = None) -> list[RetrievedChunk]:
        top_k = top_k or self.settings.RAG_TOP_K
        matches = self.vector_store.search(query_embedding, top_k)
        if not matches:
            return []

        score_by_vector_id = {match.vector_id: match.score for match in matches}
        embeddings = self.embedding_repo.list_by_vector_ids(list(score_by_vector_id.keys()))

        chunks = [
            RetrievedChunk(
                document_id=e.document_id,
                chunk_text=e.chunk_text,
                relevance_score=score_by_vector_id[e.vector_id],
            )
            for e in embeddings
        ]
        # VectorStore가 반환한 유사도 순서를 그대로 유지한다.
        chunks.sort(key=lambda c: c.relevance_score, reverse=True)
        return chunks
