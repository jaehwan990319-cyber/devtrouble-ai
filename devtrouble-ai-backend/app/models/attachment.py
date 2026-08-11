import enum

from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.mysql import CHAR
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class AttachmentFileType(str, enum.Enum):
    LOG = "LOG"
    PDF = "PDF"
    MARKDOWN = "MARKDOWN"
    IMAGE = "IMAGE"


class Attachment(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "attachments"

    document_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("trouble_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[AttachmentFileType] = mapped_column(
        Enum(AttachmentFileType, native_enum=False), nullable=False
    )
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
