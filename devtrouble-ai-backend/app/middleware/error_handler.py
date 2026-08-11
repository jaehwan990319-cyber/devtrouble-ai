"""
전역 예외 처리.

Service/Repository는 core/exceptions.py의 AppError 계열만 던지고,
여기서 유일하게 HTTP status code + 표준 응답 포맷으로 변환한다.
(Business Logic이 HTTP를 몰라야 한다는 원칙의 짝)
"""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import AppError
from app.schemas.common import ApiResponse

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=ApiResponse.fail(exc.code, exc.message).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=ApiResponse.fail("VALIDATION_ERROR", "요청 값이 올바르지 않습니다.").model_dump(),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=ApiResponse.fail("INTERNAL_ERROR", "예상치 못한 오류가 발생했습니다.").model_dump(),
        )
