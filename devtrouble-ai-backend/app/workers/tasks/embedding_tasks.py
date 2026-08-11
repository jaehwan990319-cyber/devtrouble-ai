"""
문서 생성/수정 시 트리거되는 비동기 임베딩 태스크 (FR-AI-06).

DocumentService → CeleryDocumentIndexer → 이 태스크 순으로 호출된다.
Celery 워커 프로세스에서 실행되므로 API 요청과 별도의 DB 세션을 새로 연다.
"""
from app.core.database import SessionLocal
from app.services.ai.embedding_service import EmbeddingService
from app.workers.celery_app import celery_app


@celery_app.task(name="embedding.index_document", bind=True, max_retries=3, default_retry_delay=10)
def index_document_task(self, document_id: str) -> None:
    db = SessionLocal()
    try:
        EmbeddingService(db=db).index_document(document_id)
    except Exception as exc:
        db.rollback()
        raise self.retry(exc=exc) from exc
    finally:
        db.close()


@celery_app.task(name="embedding.remove_document", bind=True, max_retries=3, default_retry_delay=10)
def remove_document_embeddings_task(self, document_id: str) -> None:
    """문서 삭제 시 document_embeddings + Vector DB의 해당 point 제거."""
    db = SessionLocal()
    try:
        EmbeddingService(db=db).remove_document(document_id)
    except Exception as exc:
        db.rollback()
        raise self.retry(exc=exc) from exc
    finally:
        db.close()
