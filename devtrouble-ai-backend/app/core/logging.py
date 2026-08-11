"""
구조화 로깅 설정.

CloudWatch에서 JSON 필드 기반 필터링이 가능하도록 JSON 포맷으로 출력한다.
"""
import logging
import sys

from app.core.config import get_settings

settings = get_settings()

_LOG_FORMAT = (
    '{"timestamp":"%(asctime)s","level":"%(levelname)s",'
    '"logger":"%(name)s","message":"%(message)s"}'
)


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))

    root_logger = logging.getLogger()
    root_logger.setLevel(settings.LOG_LEVEL)
    root_logger.handlers = [handler]

    # noisy 라이브러리 로그 레벨 조정
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
