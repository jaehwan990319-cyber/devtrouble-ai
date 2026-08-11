from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.schemas.common import ApiResponse
from app.schemas.user import UserResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=ApiResponse[UserResponse])
def get_my_profile(current_user: CurrentUser):
    return ApiResponse.ok(UserResponse.model_validate(current_user))
