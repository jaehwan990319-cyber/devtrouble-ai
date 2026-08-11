from typing import TYPE_CHECKING

from sqlalchemy import Column, ForeignKey, String, Table
from sqlalchemy.dialects.mysql import CHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.trouble_document import TroubleDocument

# document_tags는 순수 연결 테이블(추가 속성 없음)이므로 Association Table로 표현
document_tags = Table(
    "document_tags",
    Base.metadata,
    Column("document_id", CHAR(36), ForeignKey("trouble_documents.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", CHAR(36), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Tag(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "tags"

    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    documents: Mapped[list["TroubleDocument"]] = relationship(
        secondary=document_tags, back_populates="tags"
    )
