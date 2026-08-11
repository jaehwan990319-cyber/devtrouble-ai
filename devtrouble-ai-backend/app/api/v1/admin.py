from fastapi import APIRouter

from app.api.deps import AdminUser, DbSession
from app.schemas.common import ApiResponse
from app.schemas.tag import TagMergeRequest
from app.services.tag_service import TagService

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/tags/merge", response_model=ApiResponse[None])
def merge_tags(request: TagMergeRequest, admin_user: AdminUser, db: DbSession):
    service = TagService(db)
    service.merge_tags(request.source_tag_id, request.target_tag_id)
    return ApiResponse.ok(None)


# TODO(향후 필요 시): 유저 관리/문서 강제 삭제 등 관리자 기능은 별도 요청 시 재도입
