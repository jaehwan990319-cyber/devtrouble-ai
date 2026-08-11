"""
settings.AI_PROVIDER 값에 따라 올바른 Embedding Provider / LLM Client가
선택되는지 검증한다. 실제 외부 API 호출은 하지 않는다 (구조 검증만).
"""
from app.core.config import Settings
from app.services.ai.embedding_provider import (
    LocalHashEmbeddingProvider,
    OpenAiEmbeddingProvider,
    WatsonxEmbeddingProvider,
    get_embedding_provider,
)
from app.services.ai.llm_client import (
    OpenAiLlmClient,
    TemplateLlmClient,
    WatsonxLlmClient,
    get_llm_client,
)


def _settings(ai_provider: str, **overrides) -> Settings:
    defaults = {
        "DATABASE_URL": "sqlite:///:memory:",
        "REDIS_URL": "redis://localhost:6379/0",
        "CELERY_BROKER_URL": "redis://localhost:6379/1",
        "CELERY_RESULT_BACKEND": "redis://localhost:6379/2",
        "JWT_SECRET_KEY": "test-secret",
        "AI_PROVIDER": ai_provider,
        # 이 파일은 벤더 선택 로직만 검증하는 목적이라, Context Caching 래퍼는 꺼서
        # isinstance 검사가 원본 Provider/Client 타입을 그대로 볼 수 있게 한다
        # (캐싱 래퍼 자체는 tests/test_context_caching.py에서 따로 검증한다).
        "CONTEXT_CACHE_ENABLED": False,
    }
    defaults.update(overrides)
    return Settings(**defaults)


class TestEmbeddingProviderSelection:
    def test_default_is_local(self):
        settings = _settings("local")
        assert isinstance(get_embedding_provider(settings), LocalHashEmbeddingProvider)

    def test_openai_provider_selected(self):
        settings = _settings("openai", OPENAI_API_KEY="sk-fake")
        assert isinstance(get_embedding_provider(settings), OpenAiEmbeddingProvider)

    def test_watsonx_provider_selected(self):
        settings = _settings("watsonx", WATSONX_API_KEY="fake", WATSONX_PROJECT_ID="fake-project")
        provider = get_embedding_provider(settings)
        assert isinstance(provider, WatsonxEmbeddingProvider)
        assert provider.dimension == settings.WATSONX_EMBEDDING_DIMENSION
        assert settings.WATSONX_EMBEDDING_MODEL_ID in provider.model_name


class TestLlmClientSelection:
    def test_default_is_template(self):
        settings = _settings("local")
        assert isinstance(get_llm_client(settings), TemplateLlmClient)

    def test_openai_client_selected(self):
        settings = _settings("openai", OPENAI_API_KEY="sk-fake")
        assert isinstance(get_llm_client(settings), OpenAiLlmClient)

    def test_watsonx_client_selected(self):
        settings = _settings("watsonx", WATSONX_API_KEY="fake", WATSONX_PROJECT_ID="fake-project")
        assert isinstance(get_llm_client(settings), WatsonxLlmClient)


class TestTemplateLlmClientReformulate:
    """TemplateLlmClient.reformulate()의 규칙 기반 휴리스틱 자체를 검증한다."""

    def test_strips_question_filler_and_particles(self):
        client = TemplateLlmClient()
        result = client.reformulate("Redis 연결이 자꾸 끊기는데 원인이 뭘까?")

        assert "뭘까" not in result
        assert "Redis" in result
        assert "끊기는데" in result  # 어간 자체는 보존한다 (의문형 어미만 제거)

    def test_plain_statement_without_filler_is_returned_mostly_as_is(self):
        client = TemplateLlmClient()
        result = client.reformulate("이건 그냥 평범한 문장이다")

        assert result  # 빈 문자열이 되면 안 된다 (원문 폴백 보장)

    def test_never_returns_empty_string(self):
        """조사/어미를 다 제거해도 결과가 텅 비면 원문을 그대로 반환해야 한다."""
        client = TemplateLlmClient()
        result = client.reformulate("은는이가")

        assert result


class TestTemplateLlmClientRerank:
    """TemplateLlmClient.rerank()의 키워드 겹침 기반 휴리스틱을 검증한다."""

    def test_ranks_higher_overlap_chunk_first(self):
        client = TemplateLlmClient()
        chunks = ["Kafka Consumer Lag 문제", "Redis 커넥션 끊김 현상", "Redis timeout 설정 변경"]

        order = client.rerank("Redis 커넥션", chunks)

        # chunk1: "redis","커넥션" 둘 다 겹침(2) > chunk2: "redis"만 겹침(1) > chunk0: 겹침 없음(0)
        assert order == [1, 2, 0]

    def test_single_chunk_short_circuits(self):
        client = TemplateLlmClient()
        assert client.rerank("아무 질문", ["청크 하나"]) == [0]

    def test_empty_chunks_returns_empty_order(self):
        client = TemplateLlmClient()
        assert client.rerank("아무 질문", []) == []
