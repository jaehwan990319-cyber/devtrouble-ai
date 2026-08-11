from pydantic import BaseModel


class BookmarkToggleResponse(BaseModel):
    """토글 이후 최종 상태를 알려줘야 프론트엔드가 별도 조회 없이 버튼 상태를 갱신할 수 있다."""

    bookmarked: bool
