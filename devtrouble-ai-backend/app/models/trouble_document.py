from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.mysql import CHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.tag import Tag


class TroubleDocument(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "trouble_documents"

    project_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    problem_description: Mapped[str] = mapped_column(Text, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    stack_trace: Mapped[str | None] = mapped_column(Text, nullable=True)
    solution: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrospective: Mapped[str | None] = mapped_column(Text, nullable=True)
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    project: Mapped["Project"] = relationship(back_populates="documents")
    tags: Mapped[list["Tag"]] = relationship(
        secondary="document_tags", back_populates="documents"
    )

    @property
    def tag_names(self) -> list[str]:
        """schemas/document.py 응답(DocumentSummaryResponse 등)이 참조하는 편의 속성."""
        return [tag.name for tag in self.tags]

    # NOTE: FULLTEXT INDEX(title, problem_description, error_message)는
    # SQLAlchemy 모델 레벨이 아닌 Alembic 마이그레이션에서 raw DDL로 생성한다.
    # (MySQL FULLTEXT는 Core/ORM에서 직접 표현하기 번거로움)
