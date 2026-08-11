from typing import Literal

from pydantic import BaseModel, Field


class ConversationMessage(BaseModel):
    """멀티턴 대화 이력의 한 턴. 클라이언트가 이전 턴들을 그대로 담아 보낸다 (서버 세션 저장 없음)."""

    role: Literal["user", "assistant"]
    content: str


class AiSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    project_id: str | None = None  # 특정 프로젝트로 검색 범위를 좁히고 싶을 때
    # 후속 질문("그럼 그 경우엔?")을 이해하는 데 쓰인다. 서버는 대화를 저장하지 않으므로
    # 매 요청마다 클라이언트가 지금까지의 턴을 그대로 실어 보내야 한다.
    history: list[ConversationMessage] = Field(default_factory=list)


class AiCitation(BaseModel):
    document_id: str
    title: str
    relevance_score: float


class AiSearchResponse(BaseModel):
    """FR-AI-04/05: 원인 / 유사 사례 / 해결 방법 + 출처."""

    answer: str
    cause: str | None = None
    similar_cases: str | None = None
    solution: str | None = None
    citations: list[AiCitation] = Field(default_factory=list)
    # 이 질문이 트러블슈팅 관련으로 분류되었는지 (classify 노드 결과).
    on_topic: bool = True
    # 자체 검증(validate 노드)에서 "Context에 근거했다"고 판단됐는지.
    # False라면 재시도 예산을 다 썼는데도 여전히 근거가 불확실하다는 뜻이니
    # 프론트에서 "확실하지 않을 수 있습니다" 같은 경고를 붙이는 데 쓸 수 있다.
    is_grounded: bool = True
