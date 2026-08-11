from pydantic import BaseModel, ConfigDict, Field


class TagResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str


class TagMergeRequest(BaseModel):
    """관리자: 중복 태그 통합 (source → target)."""

    source_tag_id: str
    target_tag_id: str


class CommentCreateRequest(BaseModel):
    content: str = Field(min_length=1)


class CommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    author_id: str | None
    content: str
