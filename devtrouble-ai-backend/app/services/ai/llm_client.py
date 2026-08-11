"""
RAG 파이프라인 4단계: LLM 응답 생성.

PRD AI 파이프라인 대응: ... → Prompt 생성 → [LLM 응답 생성] → 출처 표시

- OpenAiLlmClient: langchain_openai.ChatOpenAI 사용.
- WatsonxLlmClient: langchain_ibm.ChatWatsonx 사용 (IBM watsonx.ai).
- TemplateLlmClient: settings.AI_PROVIDER == "local"(기본값)일 때 폴백. 실제 LLM
  생성 없이, PromptBuilder가 프롬프트에 심어둔 CONTEXT_JSON 블록을 그대로 읽어
  추출 요약(extractive) 방식으로 구조화된 답변을 조립한다. 생성형 품질은 없지만
  네트워크/API 키 없이도 RAG 파이프라인 전체 흐름(형식까지)을 검증할 수 있다.

## 구조화 출력(structured output)을 쓰는 이유

이전 버전은 "JSON으로만 답하라"고 프롬프트로 부탁하고, 응답 문자열에서 코드펜스를
벗겨가며 json.loads로 파싱했다. LLM이 지시를 안 지키면(설명을 덧붙이거나 형식이
어긋나면) 파싱이 깨졌다. `with_structured_output(RagAnswer)`을 쓰면 모델이 스키마를
어길 수 없게 강제되므로(OpenAI/watsonx 둘 다 함수 호출 기반으로 지원), 이 파싱
실패 가능성 자체가 사라진다.
"""
import json
import re
from abc import ABC, abstractmethod
from collections.abc import Iterator

from pydantic import BaseModel

from app.core.config import Settings, get_settings

_CONTEXT_JSON_PATTERN = re.compile(r"CONTEXT_JSON:\s*(\[.*\])", re.DOTALL)
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9가-힣]+")

_REFORMULATE_SYSTEM_PROMPT = (
    "사용자의 질문으로 검색했지만 관련 문서를 찾지 못했거나 결과가 부실합니다. "
    "검색에 더 적합하도록 핵심 키워드 중심으로 질문을 다시 표현하세요. "
    "다른 설명 없이 재구성된 질문 한 줄만 출력하세요."
)

_CLASSIFY_SYSTEM_PROMPT = (
    "사용자의 입력이 소프트웨어 개발/운영 트러블슈팅과 관련된 질문인지 판단하세요. "
    "인사말, 잡담, 개발과 무관한 질문이면 'no', 트러블슈팅 관련 질문이면 'yes'만 출력하세요."
)

_GROUNDED_SYSTEM_PROMPT = (
    "아래 답변이 주어진 CONTEXT_JSON의 내용에만 근거하고 있는지 판단하세요. "
    "CONTEXT에 없는 내용을 추측해서 답했다면 'no', 온전히 CONTEXT에 근거했다면 'yes'만 출력하세요."
)

_RERANK_SYSTEM_PROMPT = (
    "아래 번호가 매겨진 문서 발췌들을 질문과의 관련도가 높은 순서대로 재정렬하세요. "
    "다른 설명 없이 쉼표로 구분된 인덱스 목록만 출력하세요 (예: 2,0,1)."
)

_CONDENSE_SYSTEM_PROMPT = (
    "아래는 지금까지의 대화 이력입니다. 마지막 질문은 이전 대화 맥락에 의존하는 후속 질문일 "
    "수 있습니다(예: '그럼 그건요?', '그 경우엔 어떻게 해요?'). 이 후속 질문을 대화 이력 없이도 "
    "혼자서 이해할 수 있는 완전한 독립 질문으로 다시 쓰세요. 이미 독립적인 질문이라면 그대로 "
    "출력하세요. 다른 설명 없이 재구성된 질문 한 줄만 출력하세요."
)


class RagAnswer(BaseModel):
    """생성 단계의 구조화된 출력 계약. schemas/ai.py::AiSearchResponse의 원인/유사사례/해결방법과 1:1."""

    cause: str | None = None
    similar_cases: str | None = None
    solution: str | None = None


class LlmClient(ABC):
    @abstractmethod
    def generate(self, messages: list[dict[str, str]]) -> str:
        """messages를 받아 LLM 응답 문자열을 반환한다 (reformulate/classify/check_grounded용)."""
        raise NotImplementedError

    @abstractmethod
    def generate_structured(self, messages: list[dict[str, str]]) -> RagAnswer:
        """단일 호출로 구조화된 답변을 받는다 (스트리밍 없는 경로, RagService.search()에서 사용)."""
        raise NotImplementedError

    def stream_structured(self, messages: list[dict[str, str]]) -> Iterator[RagAnswer]:
        """
        토큰이 도착할 때마다 점점 채워지는 부분 구조화 답변을 낸다 (스트리밍 경로).
        기본 구현은 스트리밍을 지원하지 않는 것처럼 결과 하나만 낸다 — 하위 클래스가
        실제 스트리밍이 가능하면 오버라이드한다.
        """
        yield self.generate_structured(messages)

    def reformulate(self, query: str) -> str:
        """
        검색 결과가 빈약할 때 질문을 재구성한다 (RagService의 재시도 루프에서 사용).

        기본 구현은 실제 LLM(generate)에게 재구성을 요청한다. 생성 능력이 없는
        TemplateLlmClient는 이 메서드를 자체 휴리스틱으로 오버라이드한다.
        """
        messages = [
            {"role": "system", "content": _REFORMULATE_SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ]
        return self.generate(messages).strip()

    def classify(self, query: str) -> bool:
        """
        질문이 트러블슈팅 관련인지 판단한다 (True=관련 있음). 기본 구현은 LLM에게 묻는다.
        TemplateLlmClient는 생성 능력이 없으므로 규칙 기반 휴리스틱으로 오버라이드한다.
        """
        messages = [
            {"role": "system", "content": _CLASSIFY_SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ]
        return "yes" in self.generate(messages).strip().lower()

    def check_grounded(self, raw_response: str, context_json: str) -> bool:
        """
        생성된 답변이 CONTEXT에만 근거했는지 자체 검증한다 (self-critique).
        기본 구현은 LLM에게 재차 확인을 요청한다.
        """
        messages = [
            {"role": "system", "content": _GROUNDED_SYSTEM_PROMPT},
            {"role": "user", "content": f"CONTEXT_JSON: {context_json}\n\n답변: {raw_response}"},
        ]
        return "yes" in self.generate(messages).strip().lower()

    def rerank(self, query: str, chunk_texts: list[str]) -> list[int]:
        """
        chunk_texts를 질문과의 관련도 순으로 재정렬한 인덱스 리스트를 반환한다.

        기본 구현은 LLM에게 번호가 매겨진 발췌 목록을 주고 순서를 물어본 뒤, 응답에서
        숫자만 정규식으로 뽑아낸다(굳이 구조화 출력까지는 안 써도 되는 가벼운 작업이라
        간단한 텍스트 파싱으로 처리). 잘못되었거나 응답에서 빠진 인덱스는 원래 순서대로
        뒤에 붙여 항상 완전한 순열을 보장한다.
        """
        if len(chunk_texts) <= 1:
            return list(range(len(chunk_texts)))

        listing = "\n".join(f"[{i}] {text[:300]}" for i, text in enumerate(chunk_texts))
        messages = [
            {"role": "system", "content": _RERANK_SYSTEM_PROMPT},
            {"role": "user", "content": f"질문: {query}\n\n{listing}"},
        ]
        raw = self.generate(messages)
        found = [int(n) for n in re.findall(r"\d+", raw)]
        valid = [i for i in dict.fromkeys(found) if 0 <= i < len(chunk_texts)]
        missing = [i for i in range(len(chunk_texts)) if i not in valid]
        return valid + missing

    def condense_query(self, query: str, history: list[dict[str, str]]) -> str:
        """
        멀티턴 후속 질문을 대화 맥락 없이도 이해되는 완전한 질문으로 압축한다.
        (검색은 항상 이번 질문만 보므로, 이 단계 없이는 "그럼 그건요?" 같은 후속
        질문이 엉뚱한 문서를 찾게 된다.)

        기본 구현은 실제 LLM에게 재구성을 요청한다. 생성 능력이 없는 TemplateLlmClient는
        이 메서드를 자체 휴리스틱으로 오버라이드한다.
        """
        history_text = "\n".join(f"{turn['role']}: {turn['content']}" for turn in history)
        messages = [
            {"role": "system", "content": _CONDENSE_SYSTEM_PROMPT},
            {"role": "user", "content": f"대화 이력:\n{history_text}\n\n마지막 질문: {query}"},
        ]
        return self.generate(messages).strip()


class OpenAiLlmClient(LlmClient):
    """langchain_openai.ChatOpenAI 사용."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._client = None

    def _get_client(self):
        if self._client is None:
            from langchain_openai import ChatOpenAI

            self._client = ChatOpenAI(
                model=self.settings.LLM_MODEL_NAME,
                api_key=self.settings.OPENAI_API_KEY,
                temperature=0.2,
            )
        return self._client

    def generate(self, messages: list[dict[str, str]]) -> str:
        response = self._get_client().invoke(messages)
        return response.content

    def generate_structured(self, messages: list[dict[str, str]]) -> RagAnswer:
        return self._get_client().with_structured_output(RagAnswer).invoke(messages)

    def stream_structured(self, messages: list[dict[str, str]]) -> Iterator[RagAnswer]:
        yield from self._get_client().with_structured_output(RagAnswer).stream(messages)


class WatsonxLlmClient(LlmClient):
    """IBM watsonx.ai LLM 클라이언트 (langchain_ibm.ChatWatsonx 사용)."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._client = None

    def _get_client(self):
        if self._client is None:
            from langchain_ibm import ChatWatsonx

            self._client = ChatWatsonx(
                model_id=self.settings.WATSONX_LLM_MODEL_ID,
                url=self.settings.WATSONX_URL,
                project_id=self.settings.WATSONX_PROJECT_ID,
                apikey=self.settings.WATSONX_API_KEY,
                params={"temperature": 0.2},
            )
        return self._client

    def _to_tuples(self, messages: list[dict[str, str]]):
        # ChatWatsonx는 (role, content) 튜플 형태의 메시지를 기대한다
        # (langchain_openai.ChatOpenAI는 dict도 받지만, ChatWatsonx 예제는 튜플 형식을 사용).
        return [(m["role"], m["content"]) for m in messages]

    def generate(self, messages: list[dict[str, str]]) -> str:
        response = self._get_client().invoke(self._to_tuples(messages))
        return response.content

    def generate_structured(self, messages: list[dict[str, str]]) -> RagAnswer:
        return self._get_client().with_structured_output(RagAnswer).invoke(self._to_tuples(messages))

    def stream_structured(self, messages: list[dict[str, str]]) -> Iterator[RagAnswer]:
        yield from self._get_client().with_structured_output(RagAnswer).stream(self._to_tuples(messages))


class TemplateLlmClient(LlmClient):
    """OPENAI_API_KEY 없이 로컬/CI에서 파이프라인을 검증하기 위한 결정론적 폴백."""

    # 의문형 어미/조사를 제거해 핵심 키워드만 남기는 데 쓰는 패턴들.
    # LocalHashEmbeddingProvider가 Bag-of-Words 해싱이라, 의문형 어미 같은 "잡음" 토큰을
    # 없애면 실제 키워드가 벡터에서 차지하는 비중이 올라가 코사인 유사도가 개선될 수 있다.
    _FILLER_SUFFIXES = re.compile(
        r"(뭐야|뭘까|무엇인가요|인가요|일까요|왜|어떻게|해결하는지|하는지|하나요|나요|까요)\??"
    )
    _PARTICLES = re.compile(r"(이|가|은|는|을|를|에서|으로|의)(?=\s|$)")

    # 순수 잡담/인사로 간주할 짧은 패턴들. 오탐(정상 질문을 off-topic으로 잘못 분류)을
    # 피하려고 "완전히 이것들 중 하나와 일치할 때만" off-topic으로 본다 (부분 포함 매칭 X).
    _SMALL_TALK_PATTERNS = frozenset({
        "안녕", "안녕하세요", "안녕하세요?", "hi", "hello", "ㅎㅇ",
        "고마워", "고마워요", "감사합니다", "감사해요", "thanks", "thank you",
        "테스트", "test",
    })

    def generate(self, messages: list[dict[str, str]]) -> str:
        context_items = self._extract_context(messages)
        if not context_items:
            return '{"cause": null, "similar_cases": null, "solution": null}'
        answer = self._build_answer(context_items)
        return answer.model_dump_json()

    def generate_structured(self, messages: list[dict[str, str]]) -> RagAnswer:
        context_items = self._extract_context(messages)
        if not context_items:
            return RagAnswer(
                cause="관련된 과거 트러블슈팅 문서를 찾지 못했습니다.", similar_cases="", solution=""
            )
        return self._build_answer(context_items)

    def stream_structured(self, messages: list[dict[str, str]]) -> Iterator[RagAnswer]:
        """
        실제 스트리밍은 아니지만(로컬 폴백이라 진짜 토큰이 없음), 필드가 하나씩
        채워지는 것처럼 점진적으로 흉내내서 UI 스트리밍 경로 전체를 오프라인에서도
        검증할 수 있게 한다.
        """
        final = self.generate_structured(messages)
        yield RagAnswer(cause=final.cause, similar_cases=None, solution=None)
        yield RagAnswer(cause=final.cause, similar_cases=final.similar_cases, solution=None)
        yield final

    def _build_answer(self, context_items: list[dict]) -> RagAnswer:
        top = context_items[0]
        cause = self._first_sentence(top["text"])
        solution = self._extract_after_keyword(top["text"], "해결") or cause
        document_ids = list(dict.fromkeys(item["document_id"] for item in context_items))
        doc_id_list = ", ".join(document_ids)
        similar_cases = f"관련 문서 {len(context_items)}건이 검색되었습니다 (document_id: {doc_id_list})."
        return RagAnswer(cause=cause, similar_cases=similar_cases, solution=solution)

    @staticmethod
    def _extract_context(messages: list[dict[str, str]]) -> list[dict]:
        for message in reversed(messages):
            match = _CONTEXT_JSON_PATTERN.search(message.get("content", ""))
            if match:
                return json.loads(match.group(1))
        return []

    @staticmethod
    def _first_sentence(text: str, max_len: int = 200) -> str:
        stripped = text.strip().replace("\n", " ")
        first = re.split(r"(?<=[.!?。])\s", stripped, maxsplit=1)[0]
        return first[:max_len]

    @staticmethod
    def _extract_after_keyword(text: str, keyword: str) -> str | None:
        idx = text.find(keyword)
        if idx == -1:
            return None
        snippet = text[idx:idx + 200].replace("\n", " ").strip()
        return snippet

    def reformulate(self, query: str) -> str:
        """
        실제 생성 능력이 없으므로, 의문형 어미와 조사를 제거해 핵심 키워드만
        남기는 규칙 기반 휴리스틱을 쓴다. 진짜 LLM만큼 똑똑하진 않지만,
        "질문 원문 그대로 다시 검색"보다는 나은 두 번째 시도를 제공한다.
        """
        cleaned = self._FILLER_SUFFIXES.sub(" ", query)
        cleaned = self._PARTICLES.sub(" ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned or query

    def classify(self, query: str) -> bool:
        """
        생성 능력이 없으므로, 짧은 잡담/인사 패턴과 완전히 일치할 때만 off-topic으로
        본다. 오탐 위험(정상 질문을 걸러버리는 것)이 훨씬 크므로 최대한 보수적으로 판단한다.
        """
        normalized = query.strip().lower().rstrip("!.")
        return normalized not in self._SMALL_TALK_PATTERNS

    def check_grounded(self, raw_response: str, context_json: str) -> bool:
        """
        생성 능력이 없는 대신 CONTEXT를 그대로 발췌해 답하므로(extractive), 구조상 항상
        근거가 있다고 간주한다. 실제 검증이 의미 있는 쪽은 OpenAI/watsonx 같은 생성형이다.
        """
        return True

    def rerank(self, query: str, chunk_texts: list[str]) -> list[int]:
        """생성 능력이 없으므로, 질문과 겹치는 토큰 수를 세는 휴리스틱으로 재정렬한다."""
        query_tokens = set(_TOKEN_PATTERN.findall(query.lower()))

        def overlap(text: str) -> int:
            text_tokens = set(_TOKEN_PATTERN.findall(text.lower()))
            return len(query_tokens & text_tokens)

        scores = [overlap(text) for text in chunk_texts]
        return sorted(range(len(chunk_texts)), key=lambda i: scores[i], reverse=True)

    def condense_query(self, query: str, history: list[dict[str, str]]) -> str:
        """
        실제 생성 능력이 없으므로, 대화 이력 중 가장 최근 사용자 발화의 핵심 단어를
        이번 질문에 그대로 이어붙이는 방식으로 흉내낸다. LocalHashEmbeddingProvider가
        Bag-of-Words 해싱이라, 이렇게만 해도 이전 턴에서 언급된 키워드가 검색 벡터에
        반영되어 후속 질문이 관련 문서를 더 잘 찾을 수 있다.
        """
        last_user_turns = [turn["content"] for turn in history if turn["role"] == "user"]
        if not last_user_turns:
            return query
        return f"{last_user_turns[-1]} {query}"


def get_llm_client(settings: Settings | None = None) -> LlmClient:
    """
    settings.AI_PROVIDER로 어떤 벤더의 LLM 클라이언트를 쓸지 선택하는 팩토리.
    settings.CONTEXT_CACHE_ENABLED가 켜져 있으면 CachingLlmClient로 감싼다.
    """
    settings = settings or get_settings()
    if settings.AI_PROVIDER == "watsonx":
        client: LlmClient = WatsonxLlmClient(settings)
    elif settings.AI_PROVIDER == "openai":
        client = OpenAiLlmClient(settings)
    else:
        client = TemplateLlmClient()

    if settings.CONTEXT_CACHE_ENABLED:
        from app.core.cache import get_cache
        from app.services.ai.caching_llm_client import CachingLlmClient

        client = CachingLlmClient(client, get_cache(settings), settings.CONTEXT_CACHE_TTL_SECONDS)

    return client
