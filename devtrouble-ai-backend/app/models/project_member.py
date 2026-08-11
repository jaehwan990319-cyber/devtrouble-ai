import enum

from sqlalchemy import Enum, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.mysql import CHAR
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class ProjectMemberRole(str, enum.Enum):
    OWNER = "OWNER"
    MEMBER = "MEMBER"


class ProjectMember(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uk_project_user"),)

    project_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[ProjectMemberRole] = mapped_column(
        Enum(ProjectMemberRole, native_enum=False), nullable=False
    )
