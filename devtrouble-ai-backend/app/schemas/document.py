from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DocumentCreateRequest(BaseModel):
    project_id: str
    title: str = Field(min_length=1, max_length=200)
    problem_description: str
    error_message: str | None = None
    stack_trace: str | None = None
    solution: str | None = None
    retrospective: str | None = None
    tag_names: list[str] = Field(default_factory=list)


class DocumentUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    problem_description: str | None = None
    error_message: str | None = None
    stack_trace: str | None = None
    solution: str | None = None
    retrospective: str | None = None
    tag_names: list[str] | None = None


class DocumentSummaryResponse(BaseModel):
    """목록 조회용 요약 응답 (본문 전체를 내려주지 않아 트래픽 절약)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    title: str
    view_count: int
    created_at: datetime
    tag_names: list[str] = Field(default_factory=list)


class DocumentDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    author_id: str | None
    title: str
    problem_description: str
    error_message: str | None
    stack_trace: str | None
    solution: str | None
    retrospective: str | None
    view_count: int
    created_at: datetime
    updated_at: datetime
    tag_names: list[str] = Field(default_factory=list)


class DocumentSearchQuery(BaseModel):
    keyword: str | None = None
    tag: str | None = None
    error_code: str | None = None
    project_id: str | None = None
