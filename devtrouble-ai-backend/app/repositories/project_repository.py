from sqlalchemy import select

from app.models.project import Project
from app.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    model = Project

    def list_by_owner(self, owner_id: str) -> list[Project]:
        stmt = select(Project).where(
            Project.owner_id == owner_id, Project.deleted_at.is_(None)
        )
        return list(self.db.execute(stmt).scalars().all())

    # TODO(Backend 구현 단계): project_members 조인을 포함한
    # "내가 속한 프로젝트 목록" 조회 메서드 추가 예정 (FR-PROJ-03)
