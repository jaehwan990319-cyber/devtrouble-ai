"""
도메인 예외 계층.

Service/Repository는 이 예외들만 던지고, HTTP 상태코드 매핑은
middleware/error_handler.py 한 곳에서만 담당한다.
(Business Logic이 HTTP를 몰라야 한다는 Clean Architecture 원칙)
"""


class AppError(Exception):
    """모든 도메인 예외의 베이스 클래스."""

    code: str = "INTERNAL_ERROR"
    message: str = "예상치 못한 오류가 발생했습니다."
    status_code: int = 500

    def __init__(self, message: str | None = None):
        self.message = message or self.message
        super().__init__(self.message)


class NotFoundError(AppError):
    code = "NOT_FOUND"
    message = "리소스를 찾을 수 없습니다."
    status_code = 404


class DuplicateError(AppError):
    code = "DUPLICATE_RESOURCE"
    message = "이미 존재하는 리소스입니다."
    status_code = 409


class ValidationError(AppError):
    code = "VALIDATION_ERROR"
    message = "요청 값이 올바르지 않습니다."
    status_code = 422


class UnauthorizedError(AppError):
    code = "UNAUTHORIZED"
    message = "인증이 필요합니다."
    status_code = 401


class ForbiddenError(AppError):
    code = "FORBIDDEN"
    message = "접근 권한이 없습니다."
    status_code = 403
