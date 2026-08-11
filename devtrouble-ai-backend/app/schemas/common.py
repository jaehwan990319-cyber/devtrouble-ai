"""
PRD에 정의된 표준 API 응답 포맷.

    성공: {"success": true, "data": ...}
    실패: {"success": false, "error": {"code": "...", "message": "..."}}
"""
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str


class ApiResponse(BaseModel, Generic[T]):
    success: bool
    data: T | None = None
    error: ErrorDetail | None = None

    @classmethod
    def ok(cls, data: T) -> "ApiResponse[T]":
        return cls(success=True, data=data, error=None)

    @classmethod
    def fail(cls, code: str, message: str) -> "ApiResponse[None]":
        return cls(success=False, data=None, error=ErrorDetail(code=code, message=message))


class PageParams(BaseModel):
    page: int = 1
    page_size: int = 20


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
