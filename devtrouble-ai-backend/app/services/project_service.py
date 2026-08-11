"""
프로젝트 도메인 Service.

CRUD 흐름:
- create_project: 소유자를 현재 사용자로 지정해 생성
- get_project: 존재/Soft Delete 여부만 확인 (조회는 소유자가 아니어도 가능 — 팀 공유 전제)
- list_my_projects: 내가 소유한 프로젝트 목록
- update_project / delete_project: 소유자 본인만 가능

NOTE: project_members(FR-PROJ-03, 팀원 초대)는 아직 스켈레톤이다. 지금은
"소유자만 접근 가능"이라는 단순한 모델이며, 팀 공유가 필요해지면
project_members 조인으로 list_my_projects/권한 검증을 확장해야 한다.
"""
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.project import Project
from app.repositories.project_repository import ProjectRepository
from app.utils.datetime_utils import naive_utcnow


class ProjectService:
    def __init__(self, db: Session):
        self.db = db
        self.project_repo = ProjectRepository(db)

    def create_project(self, owner_id: str, name: str, description: str | None) -> Project:
        project = Project(owner_id=owner_id, name=name, description=description)
        self.project_repo.add(project)
        self.db.commit()
        self.db.refresh(project)
        return project

    def get_project(self, project_id: str) -> Project:
        return self._get_existing_project(project_id)

    def list_my_projects(self, owner_id: str) -> list[Project]:
        return self.project_repo.list_by_owner(owner_id)

    def update_project(self, project_id: str, requester_id: str, **fields) -> Project:
        project = self._get_owned_project(project_id, requester_id)

        for key, value in fields.items():
            if value is not None:
                setattr(project, key, value)

        self.db.commit()
        self.db.refresh(project)
        return project

    def delete_project(self, project_id: str, requester_id: str) -> None:
        project = self._get_owned_project(project_id, requester_id)
        project.deleted_at = naive_utcnow()
        self.db.commit()

    # --- 내부 헬퍼 ---

    def _get_existing_project(self, project_id: str) -> Project:
        project = self.project_repo.get_by_id(project_id)
        if project is None or project.deleted_at is not None:
            raise NotFoundError("프로젝트를 찾을 수 없습니다.")
        return project

    def _get_owned_project(self, project_id: str, requester_id: str) -> Project:
        project = self._get_existing_project(project_id)
        if project.owner_id != requester_id:
            raise ForbiddenError("본인이 소유한 프로젝트만 수정/삭제할 수 있습니다.")
        return project
