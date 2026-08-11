from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.common import ApiResponse
from app.schemas.project import ProjectCreateRequest, ProjectResponse, ProjectUpdateRequest
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ApiResponse[ProjectResponse], status_code=201)
def create_project(request: ProjectCreateRequest, current_user: CurrentUser, db: DbSession):
    service = ProjectService(db)
    project = service.create_project(current_user.id, request.name, request.description)
    return ApiResponse.ok(ProjectResponse.model_validate(project))


@router.get("", response_model=ApiResponse[list[ProjectResponse]])
def list_my_projects(current_user: CurrentUser, db: DbSession):
    service = ProjectService(db)
    projects = service.list_my_projects(current_user.id)
    return ApiResponse.ok(projects)


@router.get("/{project_id}", response_model=ApiResponse[ProjectResponse])
def get_project(project_id: str, db: DbSession):
    service = ProjectService(db)
    project = service.get_project(project_id)
    return ApiResponse.ok(ProjectResponse.model_validate(project))


@router.patch("/{project_id}", response_model=ApiResponse[ProjectResponse])
def update_project(project_id: str, request: ProjectUpdateRequest, current_user: CurrentUser, db: DbSession):
    service = ProjectService(db)
    project = service.update_project(project_id, current_user.id, **request.model_dump(exclude_unset=True))
    return ApiResponse.ok(ProjectResponse.model_validate(project))


@router.delete("/{project_id}", response_model=ApiResponse[None])
def delete_project(project_id: str, current_user: CurrentUser, db: DbSession):
    service = ProjectService(db)
    service.delete_project(project_id, current_user.id)
    return ApiResponse.ok(None)
