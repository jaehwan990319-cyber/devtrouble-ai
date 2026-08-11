from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.common import ApiResponse
from app.schemas.tag import CommentCreateRequest, CommentResponse
from app.services.comment_service import CommentService

router = APIRouter(prefix="/documents/{document_id}/comments", tags=["comments"])


@router.post("", response_model=ApiResponse[CommentResponse], status_code=201)
def add_comment(document_id: str, request: CommentCreateRequest, current_user: CurrentUser, db: DbSession):
    service = CommentService(db)
    comment = service.add_comment(document_id, current_user.id, request.content)
    return ApiResponse.ok(CommentResponse.model_validate(comment))


@router.get("", response_model=ApiResponse[list[CommentResponse]])
def list_comments(document_id: str, db: DbSession):
    service = CommentService(db)
    comments = service.list_comments(document_id)
    return ApiResponse.ok(comments)


@router.delete("/{comment_id}", response_model=ApiResponse[None])
def delete_comment(document_id: str, comment_id: str, current_user: CurrentUser, db: DbSession):
    service = CommentService(db)
    service.delete_comment(comment_id, current_user.id)
    return ApiResponse.ok(None)
