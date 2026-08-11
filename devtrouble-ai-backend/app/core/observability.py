"""
LangSmith 관측성 설정.

pydantic-settings는 .env 값을 Settings 객체 필드로만 읽어들이고 os.environ에는
반영하지 않는다. 그런데 LangSmith 계측(langchain/langgraph의 콜백 트레이싱)은
os.environ의 LANGCHAIN_TRACING_V2 등을 직접 읽으므로, 여기서 명시적으로
os.environ에 옮겨줘야 한다. 앱 시작 시(main.py) 한 번만 호출하면 된다.
"""
import os

from app.core.config import Settings


def configure_langsmith(settings: Settings) -> None:
    if not settings.LANGSMITH_TRACING:
        return

    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.LANGSMITH_API_KEY
    os.environ["LANGCHAIN_PROJECT"] = settings.LANGSMITH_PROJECT
    os.environ["LANGCHAIN_ENDPOINT"] = settings.LANGSMITH_ENDPOINT
