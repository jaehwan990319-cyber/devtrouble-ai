"""태그 도메인 Service — 목록 조회 + 관리자 태그 통합(FR-ETC-04)."""
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.models.tag import Tag
from app.repositories.tag_repository import TagRepository


class TagService:
    def __init__(self, db: Session):
        self.db = db
        self.tag_repo = TagRepository(db)

    def list_tags(self) -> list[Tag]:
        return self.tag_repo.list_all()

    def merge_tags(self, source_tag_id: str, target_tag_id: str) -> None:
        """
        관리자 전용: source 태그가 달린 문서를 전부 target으로 재연결한 뒤 source 태그를 삭제한다.
        (예: `db-error`, `database-error`처럼 의미가 겹치는 태그 정리)
        """
        if source_tag_id == target_tag_id:
            raise ValidationError("동일한 태그로는 병합할 수 없습니다.")

        source = self.tag_repo.get_by_id(source_tag_id)
        target = self.tag_repo.get_by_id(target_tag_id)
        if source is None or target is None:
            raise NotFoundError("병합할 태그를 찾을 수 없습니다.")

        self.tag_repo.reassign_documents(source_tag_id, target_tag_id)
        self.tag_repo.delete(source)
        self.db.commit()
