from sqlalchemy import select

from app.models.comment import Comment
from app.repositories.base import BaseRepository


class CommentRepository(BaseRepository[Comment]):
    model = Comment

    def list_by_document(self, document_id: str) -> list[Comment]:
        stmt = select(Comment).where(
            Comment.document_id == document_id, Comment.deleted_at.is_(None)
        ).order_by(Comment.created_at.asc())
        return list(self.db.execute(stmt).scalars().all())
