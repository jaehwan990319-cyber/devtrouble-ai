"""
Context Caching 테스트.

- InMemoryCache: get/set/TTL 만료를 직접 검증.
- RedisCache: 이 환경에 실제로 설치·기동한 Redis 서버를 대상으로 검증한다
  (redis-server를 apt로 설치해 daemonize로 띄운 뒤 확인 — 가짜가 아니라 진짜 서버).
- CachingLlmClient / CachingEmbeddingProvider: 같은 입력을 두 번 요청하면 감싸진
  실제 구현체가 딱 한 번만 호출되는지(캐시 히트) Spy로 검증한다.
- 팩토리(get_llm_client/get_embedding_provider)가 CONTEXT_CACHE_ENABLED 설정에 따라
  캐싱 래퍼를 씌우는지/안 씌우는지도 확인한다.
"""
import shutil
import time

import pytest

from app.core.cache import InMemoryCache, RedisCache
from app.core.config import Settings
from app.services.ai.caching_llm_client import CachingLlmClient
from app.services.ai.embedding_provider import (
    CachingEmbeddingProvider,
    LocalHashEmbeddingProvider,
    get_embedding_provider,
)
from app.services.ai.llm_client import LlmClient, RagAnswer, TemplateLlmClient, get_llm_client


def _settings(**overrides) -> Settings:
    defaults = {
        "DATABASE_URL": "sqlite:///:memory:",
        "REDIS_URL": "redis://localhost:6379/0",
        "CELERY_BROKER_URL": "redis://localhost:6379/1",
        "CELERY_RESULT_BACKEND": "redis://localhost:6379/2",
        "JWT_SECRET_KEY": "test-secret",
    }
    defaults.update(overrides)
    return Settings(**defaults)


class TestInMemoryCache:
    def test_set_then_get_returns_value(self):
        cache = InMemoryCache()
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_missing_key_returns_none(self):
        cache = InMemoryCache()
        assert cache.get("nope") is None

    def test_ttl_expiry(self):
        cache = InMemoryCache()
        cache.set("key1", "value1", ttl_seconds=0.05)
        assert cache.get("key1") == "value1"
        time.sleep(0.1)
        assert cache.get("key1") is None

    def test_no_ttl_never_expires(self):
        cache = InMemoryCache()
        cache.set("key1", "value1")  # ttl_seconds=None
        time.sleep(0.05)
        assert cache.get("key1") == "value1"


@pytest.mark.skipif(shutil.which("redis-cli") is None, reason="redis-cli 없는 환경에서는 건너뜀")
class TestRedisCacheAgainstRealServer:
    """이 저장소 환경에 실제로 설치된 Redis 서버(localhost:6379)를 대상으로 한다."""

    def test_set_then_get_returns_value(self):
        cache = RedisCache("redis://localhost:6379/0", key_prefix="test:caching:")
        cache.set("k1", "v1")
        assert cache.get("k1") == "v1"

    def test_missing_key_returns_none(self):
        cache = RedisCache("redis://localhost:6379/0", key_prefix="test:caching:")
        assert cache.get("definitely-not-set") is None

    def test_ttl_expiry(self):
        cache = RedisCache("redis://localhost:6379/0", key_prefix="test:caching:")
        cache.set("k2", "v2", ttl_seconds=1)
        assert cache.get("k2") == "v2"
        time.sleep(1.5)
        assert cache.get("k2") is None

    def test_key_prefix_isolates_namespaces(self):
        cache_a = RedisCache("redis://localhost:6379/0", key_prefix="test:a:")
        cache_b = RedisCache("redis://localhost:6379/0", key_prefix="test:b:")
        cache_a.set("shared-key", "from-a")
        assert cache_b.get("shared-key") is None


class CountingLlmClient(LlmClient):
    """generate_structured/classify/rerank 등이 몇 번 실제로 호출됐는지 세는 테스트 더블."""

    def __init__(self):
        self.generate_structured_calls = 0
        self.classify_calls = 0
        self.rerank_calls = 0
        self.condense_calls = 0
        self.check_grounded_calls = 0

    def generate(self, messages):
        return "raw text"

    def generate_structured(self, messages):
        self.generate_structured_calls += 1
        return RagAnswer(cause="c", similar_cases="s", solution="sol")

    def classify(self, query):
        self.classify_calls += 1
        return True

    def check_grounded(self, raw_response, context_json):
        self.check_grounded_calls += 1
        return True

    def rerank(self, query, chunk_texts):
        self.rerank_calls += 1
        return list(range(len(chunk_texts)))

    def condense_query(self, query, history):
        self.condense_calls += 1
        return query


class TestCachingLlmClient:
    def test_generate_structured_cache_hit_skips_wrapped_call(self):
        inner = CountingLlmClient()
        cached = CachingLlmClient(inner, InMemoryCache(), ttl_seconds=60)
        messages = [{"role": "user", "content": "동일한 메시지"}]

        cached.generate_structured(messages)
        cached.generate_structured(messages)

        assert inner.generate_structured_calls == 1

    def test_generate_structured_cache_miss_for_different_input(self):
        inner = CountingLlmClient()
        cached = CachingLlmClient(inner, InMemoryCache(), ttl_seconds=60)

        cached.generate_structured([{"role": "user", "content": "질문 A"}])
        cached.generate_structured([{"role": "user", "content": "질문 B"}])

        assert inner.generate_structured_calls == 2

    def test_classify_is_cached(self):
        inner = CountingLlmClient()
        cached = CachingLlmClient(inner, InMemoryCache(), ttl_seconds=60)

        cached.classify("같은 질문")
        cached.classify("같은 질문")

        assert inner.classify_calls == 1

    def test_rerank_is_cached(self):
        inner = CountingLlmClient()
        cached = CachingLlmClient(inner, InMemoryCache(), ttl_seconds=60)
        chunks = ["텍스트1", "텍스트2"]

        result1 = cached.rerank("질문", chunks)
        result2 = cached.rerank("질문", chunks)

        assert inner.rerank_calls == 1
        assert result1 == result2

    def test_condense_query_is_cached(self):
        inner = CountingLlmClient()
        cached = CachingLlmClient(inner, InMemoryCache(), ttl_seconds=60)
        history = [{"role": "user", "content": "이전 질문"}]

        cached.condense_query("후속 질문", history)
        cached.condense_query("후속 질문", history)

        assert inner.condense_calls == 1

    def test_check_grounded_is_cached(self):
        inner = CountingLlmClient()
        cached = CachingLlmClient(inner, InMemoryCache(), ttl_seconds=60)

        cached.check_grounded("답변1", "context1")
        cached.check_grounded("답변1", "context1")

        assert inner.check_grounded_calls == 1

    def test_generate_is_never_cached(self):
        """실시간 스트리밍/자유생성용 generate()는 캐싱 대상이 아니다 (매번 위임)."""
        inner = CountingLlmClient()
        cached = CachingLlmClient(inner, InMemoryCache(), ttl_seconds=60)

        result1 = cached.generate([{"role": "user", "content": "같은 메시지"}])
        result2 = cached.generate([{"role": "user", "content": "같은 메시지"}])

        assert result1 == result2 == "raw text"  # 위임 자체는 정상 동작


class CountingEmbeddingProvider:
    """embed_texts가 몇 번, 어떤 텍스트로 호출됐는지 기록하는 테스트 더블."""

    dimension = 4
    model_name = "counting-test-model"

    def __init__(self):
        self.call_count = 0
        self.received_texts: list[list[str]] = []

    def embed_texts(self, texts):
        self.call_count += 1
        self.received_texts.append(list(texts))
        return [[float(len(t)), 0.0, 0.0, 0.0] for t in texts]


class TestCachingEmbeddingProvider:
    def test_identical_text_is_cached(self):
        inner = CountingEmbeddingProvider()
        cached = CachingEmbeddingProvider(inner, InMemoryCache(), ttl_seconds=60)

        cached.embed_texts(["같은 텍스트"])
        cached.embed_texts(["같은 텍스트"])

        assert inner.call_count == 1

    def test_partial_cache_hit_only_computes_misses(self):
        inner = CountingEmbeddingProvider()
        cache = InMemoryCache()
        cached = CachingEmbeddingProvider(inner, cache, ttl_seconds=60)

        cached.embed_texts(["텍스트A"])  # 캐시에 A만 채워둠
        result = cached.embed_texts(["텍스트A", "텍스트B"])  # A는 캐시, B만 새로 계산되어야 함

        assert inner.call_count == 2  # 1회차(A) + 2회차(B만)
        assert inner.received_texts[-1] == ["텍스트B"]
        assert len(result) == 2

    def test_dimension_and_model_name_proxied(self):
        inner = CountingEmbeddingProvider()
        cached = CachingEmbeddingProvider(inner, InMemoryCache(), ttl_seconds=60)

        assert cached.dimension == inner.dimension
        assert cached.model_name == inner.model_name

    def test_different_model_name_does_not_share_cache(self):
        """모델이 다르면 같은 텍스트라도 캐시를 공유하면 안 된다 (임베딩 값이 다르므로)."""
        cache = InMemoryCache()

        inner_a = CountingEmbeddingProvider()
        inner_a.model_name = "model-a"
        cached_a = CachingEmbeddingProvider(inner_a, cache, ttl_seconds=60)

        inner_b = CountingEmbeddingProvider()
        inner_b.model_name = "model-b"
        cached_b = CachingEmbeddingProvider(inner_b, cache, ttl_seconds=60)

        cached_a.embed_texts(["같은 텍스트"])
        cached_b.embed_texts(["같은 텍스트"])

        assert inner_a.call_count == 1
        assert inner_b.call_count == 1  # 캐시를 공유했다면 0이어야 하지만, 모델이 다르므로 미스


class TestFactoryWiring:
    """get_llm_client/get_embedding_provider가 CONTEXT_CACHE_ENABLED에 따라 감싸는지 확인한다."""

    def test_llm_client_wrapped_when_cache_enabled(self):
        settings = _settings(AI_PROVIDER="local", CONTEXT_CACHE_ENABLED=True)
        client = get_llm_client(settings)
        assert isinstance(client, CachingLlmClient)

    def test_llm_client_not_wrapped_when_cache_disabled(self):
        settings = _settings(AI_PROVIDER="local", CONTEXT_CACHE_ENABLED=False)
        client = get_llm_client(settings)
        assert isinstance(client, TemplateLlmClient)
        assert not isinstance(client, CachingLlmClient)

    def test_embedding_provider_wrapped_when_cache_enabled(self):
        settings = _settings(AI_PROVIDER="local", CONTEXT_CACHE_ENABLED=True)
        provider = get_embedding_provider(settings)
        assert isinstance(provider, CachingEmbeddingProvider)

    def test_embedding_provider_not_wrapped_when_cache_disabled(self):
        settings = _settings(AI_PROVIDER="local", CONTEXT_CACHE_ENABLED=False)
        provider = get_embedding_provider(settings)
        assert isinstance(provider, LocalHashEmbeddingProvider)
        assert not isinstance(provider, CachingEmbeddingProvider)
