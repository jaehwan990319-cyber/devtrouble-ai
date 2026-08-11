"""
FastAPI 애플리케이션 엔트리포인트.

로컬 실행: uvicorn app.main:app --reload
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.observability import configure_langsmith
from app.middleware.error_handler import register_exception_handlers
from app.middleware.logging_middleware import LoggingMiddleware
from app.middleware.request_id import RequestIdMiddleware

settings = get_settings()
setup_logging()
configure_langsmith(settings)

app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
)

# 미들웨어는 등록 역순으로 실행되므로 RequestId → Logging 순으로 배치
app.add_middleware(LoggingMiddleware)
app.add_middleware(RequestIdMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.ENV == "local" else [],  # TODO: 운영 도메인 화이트리스트로 교체
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["health"])
def health_check():
    """ALB/EKS Liveness & Readiness Probe용 헬스체크."""
    return {"status": "ok"}
