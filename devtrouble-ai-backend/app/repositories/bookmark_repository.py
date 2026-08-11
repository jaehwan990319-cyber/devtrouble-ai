from sqlalchemy import select

from app.models.bookmark import Bookmark
from app.repositories.base import BaseRepository


class BookmarkRepository(BaseRepository[Bookmark]):
    model = Bookmark

    def get_by_user_and_document(self, user_id: str, document_id: str) -> Bookmark | None:
        stmt = select(Bookmark).where(
            Bookmark.user_id == user_id, Bookmark.document_id == document_id
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_by_user(self, user_id: str) -> list[Bookmark]:
        stmt = select(Bookmark).where(Bookmark.user_id == user_id)
        return list(self.db.execute(stmt).scalars().all())
