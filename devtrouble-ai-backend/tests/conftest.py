"""
테스트 공통 fixture.

실제 MySQL 대신 SQLite in-memory로 DB 세션을 오버라이드하여
외부 인프라 없이도 API 통합 테스트를 실행할 수 있게 한다.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import get_db
from app.main import app
from app.models import Base


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def client(db_session: Session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _reset_vector_store():
    """FaissVectorStore는 프로세스 싱글턴이므로 테스트 간 상태가 새지 않도록 매번 초기화한다."""
    from app.services.ai.vector_store import reset_vector_store_for_testing

    reset_vector_store_for_testing()
    yield
    reset_vector_store_for_testing()
