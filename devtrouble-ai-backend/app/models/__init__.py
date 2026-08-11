"""
Alembic의 `target_metadata`가 모든 테이블을 인식할 수 있도록
이 패키지를 임포트하는 것만으로 모든 모델이 등록되게 한다.

새 모델을 추가하면 반드시 이 파일에도 등록할 것.
"""
from app.models.ai_query_log import AiQueryCitation, AiQueryLog
from app.models.attachment import Attachment
from app.models.base import Base
from app.models.bookmark import Bookmark
from app.models.comment import Comment
from app.models.document_embedding import DocumentEmbedding
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.recent_view import RecentView
from app.models.refresh_token import RefreshToken
from app.models.tag import Tag, document_tags
from app.models.trouble_document import TroubleDocument
from app.models.user import User

__all__ = [
    "AiQueryCitation",
    "AiQueryLog",
    "Attachment",
    "Base",
    "Bookmark",
    "Comment",
    "DocumentEmbedding",
    "Project",
    "ProjectMember",
    "RecentView",
    "RefreshToken",
    "Tag",
    "TroubleDocument",
    "User",
    "document_tags",
]
