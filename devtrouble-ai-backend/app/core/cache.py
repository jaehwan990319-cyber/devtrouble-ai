"""
Context Caching.

RAG 파이프라인에서 같은 입력이면 같은 출력이 보장되는(결정론적으로 기대되는) LLM 호출들
(classify/check_grounded/rerank/condense_query/generate_structured)과 임베딩 계산 결과를
캐싱해서, 반복되는 질문/재시도 루프에서 불필요한 LLM 호출·비용을 줄인다.

- InMemoryCache: 프로세스 메모리 내 캐시. 개발/테스트용 — FaissVectorStore와 같은 이유로
  프로세스가 재시작되면 사라지고, 여러 워커 프로세스 간에 공유되지 않는다.
- RedisCache: 이미 Celery용으로 쓰고 있는 Redis 인프라를 그대로 재사용한다. 여러 API 서버
  인스턴스/Celery 워커가 캐시를 공유할 수 있어 운영 환경에 적합하다.
"""
import time
from abc import ABC, abstractmethod

from app.core.config import Settings, get_settings


class Cache(ABC):
    @abstractmethod
    def get(self, key: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        raise NotImplementedError


class InMemoryCache(Cache):
    def __init__(self):
        self._store: dict[str, tuple[str, float | None]] = {}

    def get(self, key: str) -> str | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at is not None and time.time() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        expires_at = time.time() + ttl_seconds if ttl_seconds else None
        self._store[key] = (value, expires_at)


class RedisCache(Cache):
    """이미 Celery 브로커로 쓰고 있는 Redis를 캐시 저장소로도 재사용한다."""

    def __init__(self, redis_url: str, key_prefix: str = "devtrouble:cache:"):
        import redis

        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._key_prefix = key_prefix

    def get(self, key: str) -> str | None:
        return self._client.get(self._key_prefix + key)

    def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        self._client.set(self._key_prefix + key, value, ex=ttl_seconds)


_cache_singleton: Cache | None = None


def get_cache(settings: Settings | None = None) -> Cache:
    """
    settings.CONTEXT_CACHE_BACKEND에 따라 InMemory/Redis 중 하나를 선택하는 팩토리.
    InMemoryCache는 프로세스 상태이므로, FaissVectorStore와 동일하게 모듈 싱글턴으로 관리한다.
    """
    global _cache_singleton
    settings = settings or get_settings()

    if _cache_singleton is None:
        if settings.CONTEXT_CACHE_BACKEND == "redis":
            _cache_singleton = RedisCache(settings.REDIS_URL)
        else:
            _cache_singleton = InMemoryCache()
    return _cache_singleton


def reset_cache_for_testing() -> None:
    """테스트 간 격리를 위해 싱글턴을 초기화한다. 프로덕션 코드에서는 호출하지 않는다."""
    global _cache_singleton
    _cache_singleton = None
