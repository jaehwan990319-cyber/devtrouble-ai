from fastapi import APIRouter, Depends

from app.api.deps import get_auth_service
from app.schemas.auth import LoginRequest, RefreshRequest, SignUpRequest, TokenPairResponse
from app.schemas.common import ApiResponse
from app.schemas.user import UserResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=ApiResponse[UserResponse], status_code=201)
def sign_up(request: SignUpRequest, auth_service: AuthService = Depends(get_auth_service)):
    user = auth_service.sign_up(request)
    return ApiResponse.ok(UserResponse.model_validate(user))


@router.post("/login", response_model=ApiResponse[TokenPairResponse])
def login(request: LoginRequest, auth_service: AuthService = Depends(get_auth_service)):
    tokens = auth_service.login(request)
    return ApiResponse.ok(tokens)


@router.post("/refresh", response_model=ApiResponse[TokenPairResponse])
def refresh(request: RefreshRequest, auth_service: AuthService = Depends(get_auth_service)):
    tokens = auth_service.refresh(request.refresh_token)
    return ApiResponse.ok(tokens)


@router.post("/logout", response_model=ApiResponse[None])
def logout(request: RefreshRequest, auth_service: AuthService = Depends(get_auth_service)):
    auth_service.logout(request.refresh_token)
    return ApiResponse.ok(None)
