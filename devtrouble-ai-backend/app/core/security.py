"""
인증 관련 순수 유틸리티.

- 비밀번호 해시/검증
- JWT Access/Refresh 토큰 발급 및 디코드

Service 계층(AuthService)에서만 호출하며, API 레이어가 직접 사용하지 않는다.

NOTE: passlib는 2020년 이후 유지보수가 중단되어 최신 bcrypt(4.1+)와
호환성 문제가 있는 것으로 확인되어(내부 self-test 단계에서 ValueError 발생),
bcrypt 라이브러리를 직접 사용한다.
"""
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

import bcrypt
import jwt

from app.core.config import get_settings

settings = get_settings()

_BCRYPT_MAX_BYTES = 72  # bcrypt 알고리즘 자체의 입력 길이 제한


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


def hash_password(plain_password: str) -> str:
    password_bytes = plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    password_bytes = plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))


def create_token(subject: str, token_type: TokenType, extra_claims: dict[str, Any] | None = None) -> str:
    """
    Access/Refresh 공용 토큰 생성기. 만료 시간만 타입에 따라 분기한다.

    jti(고유 토큰 ID)를 항상 포함한다 — iat/exp는 초 단위 정밀도라
    같은 초에 발급된 토큰은 jti 없이는 payload가 완전히 동일해질 수 있다
    (예: 로그인 직후 즉시 재발급하는 테스트/자동화 시나리오).
    """
    now = datetime.now(timezone.utc)
    if token_type is TokenType.ACCESS:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    else:
        expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type.value,
        "jti": str(uuid4()),
        "iat": now,
        "exp": expire,
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """
    유효하지 않거나 만료된 토큰이면 jwt.InvalidTokenError 계열 예외를 그대로 전파한다.
    예외 변환(→ HTTP 401)은 api/deps.py에서 처리한다.
    """
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
