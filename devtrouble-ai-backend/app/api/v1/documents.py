from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, DbSession, get_document_service
from app.schemas.common import ApiResponse
from app.schemas.document import (
    DocumentCreateRequest,
    DocumentDetailResponse,
    DocumentSummaryResponse,
    DocumentUpdateRequest,
)
from app.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=ApiResponse[DocumentDetailResponse], status_code=201)
def create_document(
    request: DocumentCreateRequest,
    current_user: CurrentUser,
    service: DocumentService = Depends(get_document_service),
):
    document = service.create_document(
        request.project_id, current_user.id, **request.model_dump(exclude={"project_id"})
    )
    return ApiResponse.ok(DocumentDetailResponse.model_validate(document))


@router.get("", response_model=ApiResponse[list[DocumentSummaryResponse]])
def search_documents(
    db: DbSession,
    keyword: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    error_code: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
):
    service = DocumentService(db)
    results = service.search_documents(keyword=keyword, tag=tag, error_code=error_code, project_id=project_id)
    return ApiResponse.ok(results)


@router.get("/{document_id}", response_model=ApiResponse[DocumentDetailResponse])
def get_document(document_id: str, db: DbSession):
    service = DocumentService(db)
    document = service.get_document(document_id)
    return ApiResponse.ok(DocumentDetailResponse.model_validate(document))


@router.patch("/{document_id}", response_model=ApiResponse[DocumentDetailResponse])
def update_document(
    document_id: str,
    request: DocumentUpdateRequest,
    current_user: CurrentUser,
    service: DocumentService = Depends(get_document_service),
):
    document = service.update_document(
        document_id, current_user.id, **request.model_dump(exclude_unset=True)
    )
    return ApiResponse.ok(DocumentDetailResponse.model_validate(document))


@router.delete("/{document_id}", response_model=ApiResponse[None])
def delete_document(
    document_id: str,
    current_user: CurrentUser,
    service: DocumentService = Depends(get_document_service),
):
    service.delete_document(document_id, current_user.id)
    return ApiResponse.ok(None)
