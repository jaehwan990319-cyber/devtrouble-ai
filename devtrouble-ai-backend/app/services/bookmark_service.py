"""즐겨찾기(FR-ETC-02) / 최근 본 문서(FR-ETC-03) 도메인 Service."""
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.bookmark import Bookmark
from app.repositories.bookmark_repository import BookmarkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.recent_view_repository import RecentViewRepository


class BookmarkService:
    def __init__(self, db: Session):
        self.db = db
        self.bookmark_repo = BookmarkRepository(db)
        self.recent_view_repo = RecentViewRepository(db)
        self.document_repo = DocumentRepository(db)

    def toggle_bookmark(self, user_id: str, document_id: str) -> bool:
        """반환값: 토글 이후 최종 상태 (True=즐겨찾기됨, False=해제됨)."""
        self._ensure_document_exists(document_id)

        existing = self.bookmark_repo.get_by_user_and_document(user_id, document_id)
        if existing is not None:
            self.bookmark_repo.delete(existing)
            self.db.commit()
            return False

        self.bookmark_repo.add(Bookmark(user_id=user_id, document_id=document_id))
        self.db.commit()
        return True

    def list_bookmarks(self, user_id: str) -> list[str]:
        # TODO: 프론트엔드가 문서 제목/태그까지 함께 보여줘야 한다면
        # document_repo.list_by_ids()와 조인해 DocumentSummaryResponse 목록으로 확장할 것.
        bookmarks = self.bookmark_repo.list_by_user(user_id)
        return [b.document_id for b in bookmarks]

    def record_view(self, user_id: str, document_id: str) -> None:
        self._ensure_document_exists(document_id)
        self.recent_view_repo.upsert(user_id, document_id)
        self.db.commit()

    def list_recent_views(self, user_id: str) -> list[str]:
        views = self.recent_view_repo.list_by_user(user_id)
        return [v.document_id for v in views]

    def _ensure_document_exists(self, document_id: str) -> None:
        document = self.document_repo.get_by_id(document_id)
        if document is None or document.deleted_at is not None:
            raise NotFoundError("문서를 찾을 수 없습니다.")
