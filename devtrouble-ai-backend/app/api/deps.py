"""
FastAPI Dependency 모음.

Repository/Service 생성과 인증 검증을 이 파일에 모아
각 라우터 함수는 `Depends(...)`로만 조립하도록 한다 (DI 원칙).
"""
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import TokenType, decode_token
from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.services.document_indexer import CeleryDocumentIndexer
from app.services.document_service import DocumentService

DbSession = Annotated[Session, Depends(get_db)]


def get_auth_service(db: DbSession) -> AuthService:
    return AuthService(db)


def get_document_service(db: DbSession) -> DocumentService:
    """
    DocumentService 조립 지점 (Composition Root).
    실제 API 요청 경로는 문서 변경 시 Celery로 비동기 색인을 트리거해야 하므로
    CeleryDocumentIndexer를 주입한다 (배치 스크립트/테스트는 기본값 NoOp를 사용).
    """
    return DocumentService(db, indexer=CeleryDocumentIndexer())


def get_current_user(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if authorization is None or not authorization.startswith("Bearer "):
        raise UnauthorizedError("인증 토큰이 필요합니다.")

    raw_token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = decode_token(raw_token)
    except Exception as exc:
        raise UnauthorizedError("유효하지 않은 토큰입니다.") from exc

    if payload.get("type") != TokenType.ACCESS.value:
        raise UnauthorizedError("Access Token이 아닙니다.")

    user = UserRepository(db).get_by_id(payload["sub"])
    if user is None:
        raise UnauthorizedError("사용자를 찾을 수 없습니다.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(current_user: CurrentUser) -> User:
    if current_user.role != UserRole.ADMIN:
        raise ForbiddenError("관리자 권한이 필요합니다.")
    return current_user


AdminUser = Annotated[User, Depends(require_admin)]
