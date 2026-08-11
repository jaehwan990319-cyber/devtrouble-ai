from sqlalchemy import delete, select

from app.models.document_embedding import DocumentEmbedding
from app.repositories.base import BaseRepository


class EmbeddingRepository(BaseRepository[DocumentEmbedding]):
    model = DocumentEmbedding

    def list_by_document(self, document_id: str) -> list[DocumentEmbedding]:
        stmt = select(DocumentEmbedding).where(DocumentEmbedding.document_id == document_id)
        return list(self.db.execute(stmt).scalars().all())

    def list_by_vector_ids(self, vector_ids: list[str]) -> list[DocumentEmbedding]:
        """VectorStore 검색 결과(vector_id)를 청크 원문/문서 ID로 역참조할 때 사용."""
        if not vector_ids:
            return []
        stmt = select(DocumentEmbedding).where(DocumentEmbedding.vector_id.in_(vector_ids))
        return list(self.db.execute(stmt).scalars().all())

    def delete_by_document(self, document_id: str) -> None:
        """문서 수정/삭제 시 기존 청크를 무효화하기 위해 사용 (재생성 전 호출)."""
        stmt = delete(DocumentEmbedding).where(DocumentEmbedding.document_id == document_id)
        self.db.execute(stmt)
        self.db.flush()
