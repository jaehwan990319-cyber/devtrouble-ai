from sqlalchemy import delete, insert, select

from app.models.tag import Tag, document_tags
from app.repositories.base import BaseRepository


class TagRepository(BaseRepository[Tag]):
    model = Tag

    def list_all(self) -> list[Tag]:
        stmt = select(Tag).order_by(Tag.name)
        return list(self.db.execute(stmt).scalars().all())

    def get_by_name(self, name: str) -> Tag | None:
        stmt = select(Tag).where(Tag.name == name)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_or_create(self, name: str) -> Tag:
        tag = self.get_by_name(name)
        if tag is None:
            tag = self.add(Tag(name=name))
        return tag

    def reassign_documents(self, source_tag_id: str, target_tag_id: str) -> None:
        """
        source_tag_id가 붙은 모든 문서를 target_tag_id로 옮긴다 (관리자 태그 통합, FR-ETC-04).

        이미 두 태그가 같은 문서에 동시에 붙어있을 수 있으므로(document_tags PK 중복 방지),
        target에 아직 없는 연결만 새로 만들고 source 쪽 연결은 전부 제거한다.
        """
        target_doc_ids = {
            row[0]
            for row in self.db.execute(
                select(document_tags.c.document_id).where(document_tags.c.tag_id == target_tag_id)
            )
        }
        source_doc_ids = [
            row[0]
            for row in self.db.execute(
                select(document_tags.c.document_id).where(document_tags.c.tag_id == source_tag_id)
            )
        ]

        rows_to_insert = [
            {"document_id": doc_id, "tag_id": target_tag_id}
            for doc_id in source_doc_ids
            if doc_id not in target_doc_ids
        ]
        if rows_to_insert:
            self.db.execute(insert(document_tags), rows_to_insert)

        self.db.execute(delete(document_tags).where(document_tags.c.tag_id == source_tag_id))
        self.db.flush()
