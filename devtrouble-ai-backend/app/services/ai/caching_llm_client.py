"""
Context Caching: LlmClient 데코레이터.

classify/check_grounded/rerank/condense_query/generate_structured는 "같은 입력이면
같은 출력"이 기대되는 호출이라 캐싱 대상으로 삼았다. 반대로 generate()/stream_structured()는
실시간 스트리밍·자유 형식 생성이라 캐싱하지 않는다 — 캐시 히트 시 토큰 스트리밍 효과 자체가
사라져 버리기 때문이다(사용자 체감 품질 저하). reformulate()도 매번 다른 실패 맥락에서
호출되어 캐시 재사용률이 낮을 것으로 보고 캐싱하지 않았다.
"""
import hashlib
import json

from app.services.ai.llm_client import LlmClient, RagAnswer


class CachingLlmClient(LlmClient):
    def __init__(self, wrapped: LlmClient, cache, ttl_seconds: int):
        self._wrapped = wrapped
        self._cache = cache
        self._ttl_seconds = ttl_seconds

    # --- 캐싱하지 않는 것들: 그대로 위임 ---

    def generate(self, messages: list[dict[str, str]]) -> str:
        return self._wrapped.generate(messages)

    def stream_structured(self, messages: list[dict[str, str]]):
        yield from self._wrapped.stream_structured(messages)

    def reformulate(self, query: str) -> str:
        return self._wrapped.reformulate(query)

    # --- 캐싱 대상 ---

    def generate_structured(self, messages: list[dict[str, str]]) -> RagAnswer:
        key = self._make_key("generate_structured", json.dumps(messages, ensure_ascii=False, sort_keys=True))
        cached = self._cache.get(key)
        if cached is not None:
            return RagAnswer.model_validate_json(cached)

        result = self._wrapped.generate_structured(messages)
        self._cache.set(key, result.model_dump_json(), self._ttl_seconds)
        return result

    def classify(self, query: str) -> bool:
        key = self._make_key("classify", query)
        cached = self._cache.get(key)
        if cached is not None:
            return cached == "1"

        result = self._wrapped.classify(query)
        self._cache.set(key, "1" if result else "0", self._ttl_seconds)
        return result

    def check_grounded(self, raw_response: str, context_json: str) -> bool:
        key = self._make_key("check_grounded", raw_response, context_json)
        cached = self._cache.get(key)
        if cached is not None:
            return cached == "1"

        result = self._wrapped.check_grounded(raw_response, context_json)
        self._cache.set(key, "1" if result else "0", self._ttl_seconds)
        return result

    def rerank(self, query: str, chunk_texts: list[str]) -> list[int]:
        key = self._make_key("rerank", query, json.dumps(chunk_texts, ensure_ascii=False))
        cached = self._cache.get(key)
        if cached is not None:
            return json.loads(cached)

        result = self._wrapped.rerank(query, chunk_texts)
        self._cache.set(key, json.dumps(result), self._ttl_seconds)
        return result

    def condense_query(self, query: str, history: list[dict[str, str]]) -> str:
        key = self._make_key("condense_query", query, json.dumps(history, ensure_ascii=False))
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        result = self._wrapped.condense_query(query, history)
        self._cache.set(key, result, self._ttl_seconds)
        return result

    @staticmethod
    def _make_key(method: str, *parts: str) -> str:
        raw = method + "|" + "|".join(parts)
        return "llm:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()
