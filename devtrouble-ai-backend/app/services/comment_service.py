"""댓글 도메인 Service (FR-ETC-01)."""
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.comment import Comment
from app.repositories.comment_repository import CommentRepository
from app.repositories.document_repository import DocumentRepository
from app.utils.datetime_utils import naive_utcnow


class CommentService:
    def __init__(self, db: Session):
        self.db = db
        self.comment_repo = CommentRepository(db)
        self.document_repo = DocumentRepository(db)

    def add_comment(self, document_id: str, author_id: str, content: str) -> Comment:
        document = self.document_repo.get_by_id(document_id)
        if document is None or document.deleted_at is not None:
            raise NotFoundError("문서를 찾을 수 없습니다.")

        comment = Comment(document_id=document_id, author_id=author_id, content=content)
        self.comment_repo.add(comment)
        self.db.commit()
        self.db.refresh(comment)
        return comment

    def list_comments(self, document_id: str) -> list[Comment]:
        return self.comment_repo.list_by_document(document_id)

    def delete_comment(self, comment_id: str, requester_id: str) -> None:
        comment = self.comment_repo.get_by_id(comment_id)
        if comment is None or comment.deleted_at is not None:
            raise NotFoundError("댓글을 찾을 수 없습니다.")
        if comment.author_id != requester_id:
            raise ForbiddenError("본인이 작성한 댓글만 삭제할 수 있습니다.")

        comment.deleted_at = naive_utcnow()
        self.db.commit()
