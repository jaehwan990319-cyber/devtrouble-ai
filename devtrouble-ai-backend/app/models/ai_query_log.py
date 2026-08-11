from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Text, func
from sqlalchemy.dialects.mysql import CHAR
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class AiQueryLog(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "ai_query_logs"

    user_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    response_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class AiQueryCitation(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "ai_query_citations"

    ai_query_log_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("ai_query_logs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("trouble_documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
