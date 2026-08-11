"""
문서 생성/수정/삭제 시 임베딩 색인을 트리거하는 인터페이스.

DocumentService가 Celery/임베딩 파이프라인에 직접 의존하지 않도록
이 인터페이스로 감싼다 — DI 원칙 + 테스트 용이성.

- NoOpDocumentIndexer: 기본값. 아무 것도 하지 않는다 (단위 테스트, 배치 스크립트 등에서 사용).
- CeleryDocumentIndexer: 운영/API 환경에서 실제로 사용. Celery 큐에 태스크를 올린다.
  큐잉 자체가 실패해도(예: Redis 일시 장애) 사용자의 CRUD 요청은 성공해야 하므로
  예외를 흡수하고 로깅만 한다 — 색인은 최종적 일관성(eventual consistency)으로 취급한다.
"""
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class DocumentIndexer(ABC):
    @abstractmethod
    def index_document(self, document_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def remove_document(self, document_id: str) -> None:
        raise NotImplementedError


class NoOpDocumentIndexer(DocumentIndexer):
    def index_document(self, document_id: str) -> None:
        pass

    def remove_document(self, document_id: str) -> None:
        pass


class CeleryDocumentIndexer(DocumentIndexer):
    def index_document(self, document_id: str) -> None:
        try:
            from app.workers.tasks.embedding_tasks import index_document_task

            index_document_task.delay(document_id)
        except Exception:
            logger.exception(
                "문서 색인 큐잉에 실패했습니다 (document_id=%s). "
                "사용자 요청은 정상 처리되었으며, 색인은 재시도/배치 보정이 필요합니다.",
                document_id,
            )

    def remove_document(self, document_id: str) -> None:
        try:
            from app.workers.tasks.embedding_tasks import remove_document_embeddings_task

            remove_document_embeddings_task.delay(document_id)
        except Exception:
            logger.exception("문서 색인 삭제 큐잉에 실패했습니다 (document_id=%s).", document_id)
