from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.mysql import CHAR
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DocumentEmbedding(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    실제 벡터 값은 Qdrant/FAISS에 저장하고, 여기서는
    청크 원문(chunk_text)과 벡터 저장소의 참조 ID(vector_id)만 보관한다.
    → MySQL: Source of Truth, Vector DB: 검색 인덱스 (역할 분리)
    """

    __tablename__ = "document_embeddings"

    document_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("trouble_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    vector_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(100), nullable=False)
