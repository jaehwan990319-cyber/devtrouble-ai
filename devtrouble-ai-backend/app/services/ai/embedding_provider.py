"""
Embedding 생성을 담당하는 Provider 계층.

RAG 파이프라인의 나머지 컴포넌트(EmbeddingService, RagService)는
이 인터페이스(EmbeddingProvider)에만 의존하고 구체 구현을 모른다 — DI 원칙.

- OpenAiEmbeddingProvider: langchain_openai로 OpenAI Embedding API 호출.
- WatsonxEmbeddingProvider: langchain_ibm으로 IBM watsonx.ai Embedding API 호출.
- LocalHashEmbeddingProvider: settings.AI_PROVIDER == "local"(기본값)일 때의
  결정론적 폴백. 실제 의미 기반 임베딩이 아니라 "hashing trick" 기반 Bag-of-Words
  벡터이므로 프로덕션 품질의 의미 검색은 제공하지 않지만, 외부 네트워크/모델
  다운로드 없이도 RAG 파이프라인 전체(청킹 → 색인 → 검색 → 응답)를 동작시키고
  테스트할 수 있게 해준다.
"""
import hashlib
import json
import math
import re
from abc import ABC, abstractmethod

from app.core.config import Settings, get_settings

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9가-힣]+")


class EmbeddingProvider(ABC):
    dimension: int
    model_name: str

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """입력 텍스트 리스트를 같은 순서의 임베딩 벡터 리스트로 변환한다."""
        raise NotImplementedError


class OpenAiEmbeddingProvider(EmbeddingProvider):
    """langchain_openai.OpenAIEmbeddings 사용."""

    dimension = 1536  # text-embedding-3-small 기준

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.model_name = self.settings.EMBEDDING_MODEL_NAME
        self._client = None  # lazy init: langchain_openai는 실제 사용 시점에만 로드

    def _get_client(self):
        if self._client is None:
            from langchain_openai import OpenAIEmbeddings

            self._client = OpenAIEmbeddings(
                model=self.settings.EMBEDDING_MODEL_NAME,
                api_key=self.settings.OPENAI_API_KEY,
            )
        return self._client

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return self._get_client().embed_documents(texts)


class WatsonxEmbeddingProvider(EmbeddingProvider):
    """
    IBM watsonx.ai Embedding Provider (langchain_ibm.WatsonxEmbeddings 사용).

    NOTE: dimension은 모델마다 다르다 (예: granite-embedding-107m-multilingual은
    384차원으로 알려져 있으나, 실제 watsonx 계정으로 직접 호출해 확인하지는 못했다 —
    다른 모델을 쓰거나 IBM이 스펙을 바꾸면 settings.WATSONX_EMBEDDING_DIMENSION을
    실제 값에 맞게 조정해야 한다. FaissVectorStore/QdrantVectorStore 둘 다 이 값을
    그대로 믿고 인덱스 차원을 고정하므로, 값이 틀리면 색인 시점에 차원 불일치 에러가 난다.
    """

    model_name_prefix = "watsonx:"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.dimension = self.settings.WATSONX_EMBEDDING_DIMENSION
        self.model_name = f"{self.model_name_prefix}{self.settings.WATSONX_EMBEDDING_MODEL_ID}"
        self._client = None

    def _get_client(self):
        if self._client is None:
            from langchain_ibm import WatsonxEmbeddings

            self._client = WatsonxEmbeddings(
                model_id=self.settings.WATSONX_EMBEDDING_MODEL_ID,
                url=self.settings.WATSONX_URL,
                project_id=self.settings.WATSONX_PROJECT_ID,
                apikey=self.settings.WATSONX_API_KEY,
            )
        return self._client

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return self._get_client().embed_documents(texts)


class LocalHashEmbeddingProvider(EmbeddingProvider):
    """
    settings.AI_PROVIDER == "local"(기본값)일 때 사용하는 결정론적 로컬 폴백.

    Feature Hashing(hashing trick)으로 각 토큰을 고정 차원 벡터의 버킷에 매핑하고
    L2 정규화한다. 같은 단어가 많이 겹치는 문서일수록 코사인 유사도가 높아지므로,
    키워드 기반의 정성적인 검색 동작 검증에는 충분하다.
    """

    dimension = 384
    model_name = "local-hash-v1"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = _TOKEN_PATTERN.findall(text.lower())
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).hexdigest()
            bucket = int(digest, 16) % self.dimension
            vector[bucket] += 1.0

        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0:
            return vector
        return [v / norm for v in vector]


class CachingEmbeddingProvider(EmbeddingProvider):
    """
    다른 EmbeddingProvider를 감싸서 Context Caching을 적용한다.

    문서 재색인(같은 텍스트를 다시 임베딩)이나, 재검색 루프에서 비슷한 질문이 반복될 때
    실제 임베딩 API를 다시 호출하지 않고 캐시된 벡터를 재사용한다. 리스트 안에서 일부만
    캐시에 있고 일부는 없는 경우(부분 캐시 히트)도 처리한다 — 캐시 미스인 것만 모아서
    한 번에 벤더 API를 호출한다.
    """

    def __init__(self, wrapped: EmbeddingProvider, cache, ttl_seconds: int):
        self._wrapped = wrapped
        self._cache = cache
        self._ttl_seconds = ttl_seconds
        self.dimension = wrapped.dimension
        self.model_name = wrapped.model_name

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float] | None] = [None] * len(texts)
        miss_indices: list[int] = []
        miss_texts: list[str] = []

        for i, text in enumerate(texts):
            cached = self._cache.get(self._make_key(text))
            if cached is not None:
                results[i] = json.loads(cached)
            else:
                miss_indices.append(i)
                miss_texts.append(text)

        if miss_texts:
            computed = self._wrapped.embed_texts(miss_texts)
            for idx, text, vector in zip(miss_indices, miss_texts, computed, strict=True):
                results[idx] = vector
                self._cache.set(self._make_key(text), json.dumps(vector), self._ttl_seconds)

        return results  # type: ignore[return-value]  # 이 시점엔 모든 원소가 채워져 있다

    def _make_key(self, text: str) -> str:
        raw = f"{self.model_name}|{text}"
        return "embed:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    """
    settings.AI_PROVIDER로 어떤 벤더의 Provider를 쓸지 선택하는 팩토리.
    api/v1/ai_search.py와 workers/tasks/embedding_tasks.py 양쪽에서 재사용한다.
    settings.CONTEXT_CACHE_ENABLED가 켜져 있으면 CachingEmbeddingProvider로 감싼다.
    """
    settings = settings or get_settings()
    if settings.AI_PROVIDER == "watsonx":
        provider: EmbeddingProvider = WatsonxEmbeddingProvider(settings)
    elif settings.AI_PROVIDER == "openai":
        provider = OpenAiEmbeddingProvider(settings)
    else:
        provider = LocalHashEmbeddingProvider()

    if settings.CONTEXT_CACHE_ENABLED:
        from app.core.cache import get_cache

        provider = CachingEmbeddingProvider(provider, get_cache(settings), settings.CONTEXT_CACHE_TTL_SECONDS)

    return provider
