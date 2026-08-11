from sqlalchemy import select

from app.models.recent_view import RecentView
from app.repositories.base import BaseRepository
from app.utils.datetime_utils import naive_utcnow


class RecentViewRepository(BaseRepository[RecentView]):
    model = RecentView

    def list_by_user(self, user_id: str, limit: int = 20) -> list[RecentView]:
        stmt = (
            select(RecentView)
            .where(RecentView.user_id == user_id)
            .order_by(RecentView.viewed_at.desc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    def upsert(self, user_id: str, document_id: str) -> RecentView:
        """
        (user_id, document_id) 유니크 제약을 이용한 upsert.

        DB 방언에 상관없이 동작하도록 조회 후 갱신/생성하는 방식으로 구현했다
        (MySQL 전용 `ON DUPLICATE KEY UPDATE` 대신 — SQLite 기반 테스트와도 호환).
        NOTE: 동시에 같은 (user_id, document_id) 조합으로 최초 조회 요청이 몰리면
        레이스 컨디션으로 유니크 제약 위반이 발생할 수 있다. 조회 이력은 정합성이
        크리티컬하지 않으므로 MVP에서는 허용 가능한 트레이드오프로 판단했다.
        """
        stmt = select(RecentView).where(
            RecentView.user_id == user_id, RecentView.document_id == document_id
        )
        existing = self.db.execute(stmt).scalar_one_or_none()
        if existing is not None:
            existing.viewed_at = naive_utcnow()
            self.db.flush()
            return existing

        record = RecentView(user_id=user_id, document_id=document_id, viewed_at=naive_utcnow())
        return self.add(record)
