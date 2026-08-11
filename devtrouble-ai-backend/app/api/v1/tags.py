from fastapi import APIRouter

from app.api.deps import DbSession
from app.schemas.common import ApiResponse
from app.schemas.tag import TagResponse
from app.services.tag_service import TagService

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("", response_model=ApiResponse[list[TagResponse]])
def list_tags(db: DbSession):
    service = TagService(db)
    tags = service.list_tags()
    return ApiResponse.ok(tags)
