"""
재랭킹(rerank)을 LlmClient에서 분리한 독립 컴포넌트.

기존에는 RagService가 LlmClient.rerank()를 직접 불렀는데, "일반 채팅 LLM에게
순서를 물어보는 방식"과 "전용 재랭킹 모델(Cohere Rerank 등)을 쓰는 방식"은
LLM 벤더(OpenAI/watsonx/local)와는 독립적인 별개의 선택이라, EmbeddingProvider/
VectorStore/LlmClient와 같은 패턴으로 분리했다 (settings.RERANK_PROVIDER로 선택).
"""
from abc import ABC, abstractmethod

from app.core.config import Settings, get_settings
from app.services.ai.llm_client import LlmClient


class Reranker(ABC):
    @abstractmethod
    def rerank(self, query: str, chunk_texts: list[str]) -> list[int]:
        """chunk_texts를 질문과의 관련도 순으로 재정렬한 인덱스 리스트를 반환한다."""
        raise NotImplementedError


class LlmReranker(Reranker):
    """일반 채팅 LLM에게 순서를 물어보는 방식 (기본값). LlmClient.rerank()에 위임한다."""

    def __init__(self, llm_client: LlmClient):
        self.llm_client = llm_client

    def rerank(self, query: str, chunk_texts: list[str]) -> list[int]:
        return self.llm_client.rerank(query, chunk_texts)


class CohereReranker(Reranker):
    """
    전용 재랭킹 모델(Cohere Rerank) 사용. 채팅 LLM에게 텍스트로 순서를 부탁하는 것보다
    이 작업에 특화되어 있어 더 정확하고 빠르고 저렴하다.

    NOTE: 이 저장소 환경에는 실제 Cohere API 키가 없어, `cohere.Client(...).rerank(...)`가
    파라미터 검증을 통과하고 실제 네트워크 호출까지 도달하는 것만 확인했다
    (watsonx 검증 때와 동일한 방식/한계).
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._client = None

    def _get_client(self):
        if self._client is None:
            import cohere

            self._client = cohere.Client(self.settings.COHERE_API_KEY)
        return self._client

    def rerank(self, query: str, chunk_texts: list[str]) -> list[int]:
        if len(chunk_texts) <= 1:
            return list(range(len(chunk_texts)))

        response = self._get_client().rerank(
            query=query,
            documents=chunk_texts,
            model=self.settings.COHERE_RERANK_MODEL,
            top_n=len(chunk_texts),
        )
        return [result.index for result in response.results]


def get_reranker(llm_client: LlmClient, settings: Settings | None = None) -> Reranker:
    """settings.RERANK_PROVIDER로 어떤 재랭킹 구현을 쓸지 선택하는 팩토리."""
    settings = settings or get_settings()
    if settings.RERANK_PROVIDER == "cohere":
        return CohereReranker(settings)
    return LlmReranker(llm_client)
