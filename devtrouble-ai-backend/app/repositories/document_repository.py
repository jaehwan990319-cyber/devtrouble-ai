from sqlalchemy import or_, select

from app.models.tag import Tag
from app.models.trouble_document import TroubleDocument
from app.repositories.base import BaseRepository
from app.schemas.document import DocumentSearchQuery


class DocumentRepository(BaseRepository[TroubleDocument]):
    model = TroubleDocument

    def list_by_project(self, project_id: str) -> list[TroubleDocument]:
        stmt = select(TroubleDocument).where(
            TroubleDocument.project_id == project_id,
            TroubleDocument.deleted_at.is_(None),
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_by_ids(self, document_ids: list[str]) -> list[TroubleDocument]:
        """RAG 인용 표시(FR-AI-05)에서 document_id → title 매핑을 만들 때 사용."""
        if not document_ids:
            return []
        stmt = select(TroubleDocument).where(TroubleDocument.id.in_(document_ids))
        return list(self.db.execute(stmt).scalars().all())

    def search(self, query: DocumentSearchQuery) -> list[TroubleDocument]:
        """
        FR-SEARCH-01(키워드) / FR-SEARCH-02(태그) / FR-SEARCH-03(에러코드) 대응.

        키워드/에러코드 검색은 LIKE 기반으로 구현했다 (DB 무관 이식성 우선).
        운영 규모에서 성능이 문제가 되면 ERD 설계 노트에 남긴 대로
        MySQL FULLTEXT 인덱스 또는 OpenSearch 도입을 검토한다.
        """
        stmt = select(TroubleDocument).where(TroubleDocument.deleted_at.is_(None))

        if query.project_id:
            stmt = stmt.where(TroubleDocument.project_id == query.project_id)

        if query.keyword:
            pattern = f"%{query.keyword}%"
            stmt = stmt.where(
                or_(
                    TroubleDocument.title.ilike(pattern),
                    TroubleDocument.problem_description.ilike(pattern),
                    TroubleDocument.error_message.ilike(pattern),
                )
            )

        if query.error_code:
            stmt = stmt.where(TroubleDocument.error_message.ilike(f"%{query.error_code}%"))

        if query.tag:
            stmt = stmt.join(TroubleDocument.tags).where(Tag.name == query.tag)

        stmt = stmt.order_by(TroubleDocument.created_at.desc()).distinct()
        return list(self.db.execute(stmt).scalars().all())
