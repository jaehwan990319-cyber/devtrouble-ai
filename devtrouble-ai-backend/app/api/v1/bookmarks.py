from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.bookmark import BookmarkToggleResponse
from app.schemas.common import ApiResponse
from app.services.bookmark_service import BookmarkService

router = APIRouter(prefix="/bookmarks", tags=["bookmarks"])


@router.post("/{document_id}", response_model=ApiResponse[BookmarkToggleResponse])
def toggle_bookmark(document_id: str, current_user: CurrentUser, db: DbSession):
    service = BookmarkService(db)
    bookmarked = service.toggle_bookmark(current_user.id, document_id)
    return ApiResponse.ok(BookmarkToggleResponse(bookmarked=bookmarked))


@router.get("", response_model=ApiResponse[list[str]])
def list_bookmarks(current_user: CurrentUser, db: DbSession):
    service = BookmarkService(db)
    bookmarks = service.list_bookmarks(current_user.id)
    return ApiResponse.ok(bookmarks)


@router.post("/recent-views/{document_id}", response_model=ApiResponse[None])
def record_recent_view(document_id: str, current_user: CurrentUser, db: DbSession):
    """
    문서 상세 화면에 진입했을 때 프론트엔드가 호출해 "최근 본 문서"에 기록한다.
    (문서 조회 자체는 인증 없이도 가능하므로, 조회수 증가와는 별개로 로그인 사용자만 이력이 남는다.)
    """
    service = BookmarkService(db)
    service.record_view(current_user.id, document_id)
    return ApiResponse.ok(None)


@router.get("/recent-views", response_model=ApiResponse[list[str]])
def list_recent_views(current_user: CurrentUser, db: DbSession):
    service = BookmarkService(db)
    views = service.list_recent_views(current_user.id)
    return ApiResponse.ok(views)
