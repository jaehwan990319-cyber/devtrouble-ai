"""
트러블 문서 도메인 Service.

CRUD 흐름:
- create_document: 프로젝트 존재 검증 → 태그 upsert → 문서 생성 → 비동기 색인 트리거
- get_document: 조회 + 조회수 증가
- update_document: 작성자 본인만 수정 가능, tag_names가 오면 태그 전체 교체 → 재색인 트리거
- delete_document: 작성자 본인만 Soft Delete → 색인 제거 트리거
- search_documents: 키워드/태그/에러코드/프로젝트 기준 검색 (FR-SEARCH-01~03)

indexer는 기본값 NoOpDocumentIndexer로, 단위 테스트에서 Celery/임베딩 파이프라인 없이도
CRUD 로직만 독립적으로 검증할 수 있다. 실제 API 요청 경로는
api/deps.py의 get_document_service()가 CeleryDocumentIndexer를 주입한다 (DI 조립 지점).
"""
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.trouble_document import TroubleDocument
from app.repositories.document_repository import DocumentRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.tag_repository import TagRepository
from app.schemas.document import DocumentSearchQuery
from app.services.document_indexer import DocumentIndexer, NoOpDocumentIndexer
from app.utils.datetime_utils import naive_utcnow


class DocumentService:
    def __init__(self, db: Session, indexer: DocumentIndexer | None = None):
        self.db = db
        self.document_repo = DocumentRepository(db)
        self.project_repo = ProjectRepository(db)
        self.tag_repo = TagRepository(db)
        self.indexer = indexer or NoOpDocumentIndexer()

    def create_document(
        self,
        project_id: str,
        author_id: str,
        title: str,
        problem_description: str,
        error_message: str | None = None,
        stack_trace: str | None = None,
        solution: str | None = None,
        retrospective: str | None = None,
        tag_names: list[str] | None = None,
    ) -> TroubleDocument:
        project = self.project_repo.get_by_id(project_id)
        if project is None or project.deleted_at is not None:
            raise NotFoundError("프로젝트를 찾을 수 없습니다.")

        tags = [self.tag_repo.get_or_create(name) for name in (tag_names or [])]

        document = TroubleDocument(
            project_id=project_id,
            author_id=author_id,
            title=title,
            problem_description=problem_description,
            error_message=error_message,
            stack_trace=stack_trace,
            solution=solution,
            retrospective=retrospective,
            tags=tags,
        )
        self.document_repo.add(document)
        self.db.commit()
        self.db.refresh(document)

        self.indexer.index_document(document.id)
        return document

    def get_document(self, document_id: str) -> TroubleDocument:
        document = self._get_existing_document(document_id)

        # NOTE: 동시 조회 시 정확한 카운트가 중요해지면
        # `UPDATE ... SET view_count = view_count + 1` 원자적 쿼리로 교체할 것.
        document.view_count += 1
        self.db.commit()
        self.db.refresh(document)
        return document

    def update_document(self, document_id: str, requester_id: str, **fields) -> TroubleDocument:
        document = self._get_owned_document(document_id, requester_id)

        tag_names = fields.pop("tag_names", None)
        for key, value in fields.items():
            if value is not None:
                setattr(document, key, value)

        if tag_names is not None:
            document.tags = [self.tag_repo.get_or_create(name) for name in tag_names]

        self.db.commit()
        self.db.refresh(document)

        self.indexer.index_document(document.id)
        return document

    def delete_document(self, document_id: str, requester_id: str) -> None:
        document = self._get_owned_document(document_id, requester_id)
        document.deleted_at = naive_utcnow()
        self.db.commit()

        self.indexer.remove_document(document_id)

    def search_documents(
        self,
        keyword: str | None = None,
        tag: str | None = None,
        error_code: str | None = None,
        project_id: str | None = None,
    ) -> list[TroubleDocument]:
        query = DocumentSearchQuery(
            keyword=keyword, tag=tag, error_code=error_code, project_id=project_id
        )
        return self.document_repo.search(query)

    # --- 내부 헬퍼 ---

    def _get_existing_document(self, document_id: str) -> TroubleDocument:
        document = self.document_repo.get_by_id(document_id)
        if document is None or document.deleted_at is not None:
            raise NotFoundError("트러블 문서를 찾을 수 없습니다.")
        return document

    def _get_owned_document(self, document_id: str, requester_id: str) -> TroubleDocument:
        document = self._get_existing_document(document_id)
        if document.author_id != requester_id:
            raise ForbiddenError("본인이 작성한 문서만 수정/삭제할 수 있습니다.")
        return document
