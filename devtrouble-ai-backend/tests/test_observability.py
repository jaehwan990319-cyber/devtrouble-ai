"""configure_langsmith()가 설정에 따라 os.environ을 올바르게 채우는지/비우는지 검증한다."""
import os

from app.core.config import Settings
from app.core.observability import configure_langsmith


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


class TestConfigureLangsmith:
    def test_disabled_by_default_does_not_touch_environ(self):
        for key in ("LANGCHAIN_TRACING_V2", "LANGCHAIN_API_KEY", "LANGCHAIN_PROJECT"):
            os.environ.pop(key, None)

        configure_langsmith(_settings(LANGSMITH_TRACING=False))

        assert "LANGCHAIN_TRACING_V2" not in os.environ

    def test_enabled_sets_expected_environ_vars(self):
        configure_langsmith(
            _settings(
                LANGSMITH_TRACING=True,
                LANGSMITH_API_KEY="ls-fake-key",
                LANGSMITH_PROJECT="my-project",
                LANGSMITH_ENDPOINT="https://custom.smith.example.com",
            )
        )

        assert os.environ["LANGCHAIN_TRACING_V2"] == "true"
        assert os.environ["LANGCHAIN_API_KEY"] == "ls-fake-key"
        assert os.environ["LANGCHAIN_PROJECT"] == "my-project"
        assert os.environ["LANGCHAIN_ENDPOINT"] == "https://custom.smith.example.com"

        # 테스트 간 오염 방지
        for key in ("LANGCHAIN_TRACING_V2", "LANGCHAIN_API_KEY", "LANGCHAIN_PROJECT", "LANGCHAIN_ENDPOINT"):
            os.environ.pop(key, None)
