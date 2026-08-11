"""
인증 도메인 Service.

- Business Logic은 여기에만 둔다 (API 레이어는 얇게 유지).
- Repository를 통해서만 DB에 접근한다.
- 이 파일은 다른 도메인 Service 구현 시 참조할 표준 패턴이다.
"""
from datetime import timedelta
from hashlib import sha256

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import DuplicateError, UnauthorizedError
from app.core.security import TokenType, create_token, decode_token, hash_password, verify_password
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginRequest, SignUpRequest, TokenPairResponse
from app.utils.datetime_utils import naive_utcnow


def _hash_token(raw_token: str) -> str:
    """Refresh Token은 탈취 시 피해를 줄이기 위해 원문이 아닌 해시로 저장한다."""
    return sha256(raw_token.encode("utf-8")).hexdigest()


class AuthService:
    def __init__(self, db: Session, settings: Settings | None = None):
        self.db = db
        self.settings = settings or get_settings()
        self.user_repo = UserRepository(db)

    def sign_up(self, request: SignUpRequest) -> User:
        """FR-AUTH-01: 이메일 중복 검증 후 비밀번호를 해시하여 저장한다."""
        if self.user_repo.exists_by_email(request.email):
            raise DuplicateError("이미 가입된 이메일입니다.")

        user = User(
            email=request.email,
            password_hash=hash_password(request.password),
            nickname=request.nickname,
        )
        self.user_repo.add(user)
        self.db.commit()
        return user

    def login(self, request: LoginRequest) -> TokenPairResponse:
        """FR-AUTH-02: 인증 성공 시 Access/Refresh 토큰 쌍을 발급한다."""
        user = self.user_repo.get_by_email(request.email)
        if user is None or not verify_password(request.password, user.password_hash):
            # 이메일 존재 여부를 노출하지 않기 위해 두 실패 사유를 같은 메시지로 통일
            raise UnauthorizedError("이메일 또는 비밀번호가 올바르지 않습니다.")

        return self._issue_token_pair(user)

    def refresh(self, raw_refresh_token: str) -> TokenPairResponse:
        """
        FR-AUTH-03: Refresh Token으로 새 Access/Refresh 쌍을 발급한다.

        Refresh Token Rotation을 적용한다 — 사용된 Refresh Token은 즉시 폐기하여
        토큰이 탈취되었을 때 재사용(replay)되는 것을 막는다.
        """
        payload = self._decode_refresh_token(raw_refresh_token)

        stored = self._get_valid_stored_token(raw_refresh_token)
        if stored is None:
            raise UnauthorizedError("만료되었거나 폐기된 Refresh Token입니다.")

        user = self.user_repo.get_by_id(payload["sub"])
        if user is None:
            raise UnauthorizedError("사용자를 찾을 수 없습니다.")

        stored.revoked = True
        self.db.flush()
        return self._issue_token_pair(user)

    def logout(self, raw_refresh_token: str) -> None:
        """FR-AUTH-04: 로그아웃 시 해당 Refresh Token을 즉시 폐기한다."""
        token_hash = _hash_token(raw_refresh_token)
        stored = (
            self.db.query(RefreshToken)
            .filter(RefreshToken.token_hash == token_hash)
            .one_or_none()
        )
        if stored is not None:
            stored.revoked = True
            self.db.commit()

    # --- 내부 헬퍼 ---

    def _decode_refresh_token(self, raw_refresh_token: str) -> dict:
        try:
            payload = decode_token(raw_refresh_token)
        except Exception as exc:  # jwt 예외 계열 → 도메인 예외로 변환
            raise UnauthorizedError("유효하지 않은 Refresh Token입니다.") from exc

        if payload.get("type") != TokenType.REFRESH.value:
            raise UnauthorizedError("Refresh Token 타입이 아닙니다.")
        return payload

    def _get_valid_stored_token(self, raw_refresh_token: str) -> RefreshToken | None:
        token_hash = _hash_token(raw_refresh_token)
        stored = (
            self.db.query(RefreshToken)
            .filter(RefreshToken.token_hash == token_hash, RefreshToken.revoked.is_(False))
            .one_or_none()
        )
        if stored is None or stored.expires_at < naive_utcnow():
            return None
        return stored

    def _issue_token_pair(self, user: User) -> TokenPairResponse:
        access_token = create_token(
            subject=user.id, token_type=TokenType.ACCESS, extra_claims={"role": user.role.value}
        )
        refresh_token = create_token(subject=user.id, token_type=TokenType.REFRESH)

        expires_at = naive_utcnow() + timedelta(days=self.settings.REFRESH_TOKEN_EXPIRE_DAYS)
        self.db.add(
            RefreshToken(
                user_id=user.id,
                token_hash=_hash_token(refresh_token),
                expires_at=expires_at,
                created_at=naive_utcnow(),
            )
        )
        self.db.commit()

        return TokenPairResponse(access_token=access_token, refresh_token=refresh_token)
