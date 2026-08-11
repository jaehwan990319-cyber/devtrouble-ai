"""
애플리케이션 전역 설정.

- 모든 값은 환경변수(.env / Helm ConfigMap·Secret)에서 주입받는다.
- 코드에 Magic Number/문자열을 두지 않는다는 원칙에 따라
  기본값이 필요한 경우에도 이 파일에서만 정의한다.
"""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    APP_NAME: str = "DevTrouble AI"
    ENV: Literal["local", "dev", "staging", "prod"] = "local"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # --- Database ---
    DATABASE_URL: str  # 예: mysql+pymysql://user:pw@host:3306/devtrouble
    DATABASE_POOL_SIZE: int = 10
    DATABASE_POOL_RECYCLE_SECONDS: int = 1800

    # --- Redis / Celery ---
    REDIS_URL: str  # 예: redis://redis:6379/0
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str

    # --- JWT ---
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14

    # --- AWS ---
    AWS_REGION: str = "ap-northeast-2"
    S3_BUCKET_NAME: str = ""

    # --- Vector DB / AI ---
    VECTOR_DB_PROVIDER: Literal["faiss", "chroma", "qdrant"] = "faiss"
    QDRANT_URL: str = ""
    QDRANT_COLLECTION_NAME: str = "trouble_documents"
    CHROMA_PERSIST_DIR: str = "./chroma_data"
    CHROMA_COLLECTION_NAME: str = "trouble_documents"

    # 어떤 벤더로 임베딩/LLM을 생성할지. "local"은 API 키 없이 오프라인 폴백을 강제로 사용한다.
    # (services/ai/embedding_provider.py, services/ai/llm_client.py 참고)
    AI_PROVIDER: Literal["local", "openai", "watsonx"] = "local"

    OPENAI_API_KEY: str = ""
    EMBEDDING_MODEL_NAME: str = "text-embedding-3-small"
    LLM_MODEL_NAME: str = "gpt-4o-mini"

    # --- IBM watsonx.ai ---
    WATSONX_API_KEY: str = ""
    WATSONX_PROJECT_ID: str = ""
    WATSONX_URL: str = "https://us-south.ml.cloud.ibm.com"
    WATSONX_EMBEDDING_MODEL_ID: str = "ibm/granite-embedding-107m-multilingual"
    WATSONX_EMBEDDING_DIMENSION: int = 384
    WATSONX_LLM_MODEL_ID: str = "meta-llama/llama-3-3-70b-instruct"

    RAG_TOP_K: int = 5
    # 검색 결과가 빈약할 때 질문을 재구성해 재시도하는 횟수 (0이면 재시도 없음).
    RAG_MAX_RETRIEVAL_ATTEMPTS: int = 1
    # 최고 유사도 점수가 이 값 미만이면 "결과가 빈약하다"고 판단해 재시도한다.
    # NOTE: 임베딩 벤더마다 코사인 유사도 분포가 크게 다르다 (LocalHash는 대략 0~0.3,
    # OpenAI/watsonx 실제 임베딩은 대략 0.5~0.95 범위가 흔하다). 기본값 0.05는 두 경우 모두
    # "사실상 아무 신호도 없는" 수준만 걸러내도록 보수적으로 잡았다 — 실제 임베딩을 쓰면서
    # 품질 기준을 더 엄격하게 걸고 싶다면 0.5 안팎으로 올리는 것을 고려할 것.
    RAG_RETRY_SCORE_THRESHOLD: float = 0.05
    # 하이브리드 검색: 벡터 검색이 놓친 문서도 키워드(LIKE) 검색으로 보완할 때,
    # 키워드로만 찾은 문서에 부여하는 관련도 점수. 정확한 문자열 포함 매칭이므로
    # RAG_RETRY_SCORE_THRESHOLD보다 확실히 높게 잡아 "충분한 결과"로 인정되게 한다.
    RAG_KEYWORD_MATCH_SCORE: float = 0.5

    # --- 멀티턴: 후속 질문 압축(query condensation) ---
    # 대화 이력이 있을 때만 켜진다(history가 없으면 LLM 호출 자체를 안 함).
    RAG_ENABLE_QUERY_CONDENSATION: bool = True

    # --- 재랭킹 벤더 ---
    # "llm"(기본값)은 일반 채팅 LLM에게 순서를 물어본다. "cohere"는 전용 재랭킹 모델을 쓴다
    # (더 정확하고 빠르고 저렴하지만 별도 API 키가 필요하다).
    RERANK_PROVIDER: Literal["llm", "cohere"] = "llm"
    COHERE_API_KEY: str = ""
    COHERE_RERANK_MODEL: str = "rerank-v3.5"

    # --- LangSmith (관측성) ---
    # true로 켜면 LangChain/LangGraph 호출이 전부 LangSmith 대시보드에 자동으로 기록된다.
    # (LlmClient의 실제 LLM 호출부가 langchain_openai/langchain_ibm을 쓰므로 코드 변경 없이 계측됨)
    LANGSMITH_TRACING: bool = False
    LANGSMITH_API_KEY: str = ""
    LANGSMITH_PROJECT: str = "devtrouble-ai"
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"

    # --- 비용 최적화: 선택적 RAG 단계 끄기 ---
    # 각각 classify/rerank/validate 노드가 LLM을 호출하는 걸 건너뛸 수 있게 하는 토글.
    # 기본값은 전부 켜짐(현재 동작 유지)이며, 트래픽이 신뢰할 수 있거나(classify 불필요),
    # 재랭킹/자체검증의 정확도 이득보다 비용이 더 부담될 때 끄는 용도다.
    RAG_ENABLE_CLASSIFY: bool = True
    RAG_ENABLE_RERANK: bool = True
    RAG_ENABLE_VALIDATION: bool = True

    # --- Context Caching ---
    # classify/check_grounded/rerank/condense_query/generate_structured 처럼 "같은 입력이면
    # 같은 출력"이 기대되는 LLM 호출과 임베딩 계산 결과를 캐싱한다. generate()/stream_structured()
    # 자체(실시간 스트리밍)는 캐싱하지 않는다.
    CONTEXT_CACHE_ENABLED: bool = True
    # "memory"(기본값, 프로세스 로컬) | "redis"(이미 쓰고 있는 Celery Redis를 재사용, 여러
    # 프로세스/워커가 캐시를 공유하고 싶을 때 — 운영 환경에 권장)
    CONTEXT_CACHE_BACKEND: Literal["memory", "redis"] = "memory"
    CONTEXT_CACHE_TTL_SECONDS: int = 3600

    # --- Logging ---
    LOG_LEVEL: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """
    설정 객체는 프로세스 내에서 1회만 생성해 재사용한다.
    FastAPI Dependency로 주입하기 위해 lru_cache로 싱글턴화.
    """
    return Settings()
