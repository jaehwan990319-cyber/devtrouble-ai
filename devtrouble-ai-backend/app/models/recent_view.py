from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.mysql import CHAR
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class RecentView(Base, UUIDPrimaryKeyMixin):
    """
    조회 시마다 row를 쌓지 않고 (user_id, document_id) 기준
    upsert로 viewed_at만 갱신한다 (ERD 설계 노트 참고).
    """

    __tablename__ = "recent_views"
    __table_args__ = (UniqueConstraint("user_id", "document_id", name="uk_recentview_user_doc"),)

    user_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("trouble_documents.id", ondelete="CASCADE"), nullable=False
    )
    viewed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
