"""
Celery 앱 진입점.

실행 예: celery -A app.workers.celery_app worker --loglevel=info
"""
from celery import Celery

from app.core.config import get_settings
from app.core.observability import configure_langsmith

settings = get_settings()
configure_langsmith(settings)

celery_app = Celery(
    "devtrouble_ai",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks.embedding_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Seoul",
    enable_utc=True,
    # Redis가 아예 없는 환경(로컬 개발 등)에서 .delay() 호출이 빠르게 실패하도록 설정.
    # kombu의 기본 재시도 정책은 최대 20회까지 1초 간격으로 재시도해서, 문서 저장할
    # 때마다 최대 ~20초씩 멈추는 문제가 있었다 — CeleryDocumentIndexer는 큐잉 실패를
    # 예외로 흡수하고 즉시 넘어가도록 설계했는데, 그 예외 자체가 늦게 발생하면 설계
    # 의도(색인 실패해도 사용자 요청은 안 막힘)가 무색해진다.
    broker_connection_retry_on_startup=False,
    broker_connection_retry=False,
    broker_connection_max_retries=0,
    result_backend_transport_options={"retry_policy": {"max_retries": 1}},
)
