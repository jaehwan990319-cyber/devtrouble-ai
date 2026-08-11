"""
SQLAlchemy Engine / Session 관리.

Repository 계층은 이 모듈이 제공하는 Session만 알고,
Connection 생성 방식(pool 설정 등)에는 의존하지 않는다.
"""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    pool_recycle=settings.DATABASE_POOL_RECYCLE_SECONDS,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI Dependency: 요청 단위 세션을 생성하고 반드시 닫는다."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
