"""
RAG 파이프라인 3단계: 검색된 Context로 LLM 프롬프트 생성.

PRD AI 파이프라인 대응: ... → Top K 문서 검색 → [Prompt 생성] → LLM 응답 생성 → ...

시스템 프롬프트는 JSON 구조화 출력을 강제하여 schemas/ai.py의
AiSearchResponse(cause/similar_cases/solution)와 1:1로 매핑되도록 한다.

CONTEXT_JSON 블록은 사람이 읽는 문장 안에 기계가 파싱 가능한 JSON을 함께 심어,
실제 LLM(OpenAiLlmClient)에게는 자연스러운 컨텍스트로 동작하면서
오프라인 폴백(TemplateLlmClient)도 같은 데이터를 정확히 재사용할 수 있게 한다.
"""
import json

from app.services.ai.retriever_service import RetrievedChunk

_SYSTEM_PROMPT = (
    "당신은 개발자 트러블슈팅 어시스턴트입니다. "
    "주어진 CONTEXT(과거 트러블슈팅 문서 발췌)만을 근거로 답변하세요. "
    "Context에 없는 내용은 추측하지 마세요. "
    "반드시 다음 키를 가진 JSON 객체 하나만 출력하세요 (다른 텍스트 금지): "
    '{"cause": "...", "similar_cases": "...", "solution": "..."}'
)


class PromptBuilder:
    def build(
        self,
        question: str,
        chunks: list[RetrievedChunk],
        document_titles: dict[str, str] | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> list[dict[str, str]]:
        """
        OpenAI/LangChain 메시지 포맷(list[{"role": ..., "content": ...}])으로 반환.

        history는 [{"role": "user"|"assistant", "content": "..."}] 형태의 이전 턴들이다.
        시스템 프롬프트 다음, 이번 질문(CONTEXT_JSON 포함) 이전에 그대로 끼워 넣어
        LLM이 후속 질문("그럼 그 경우엔?")의 맥락을 이해할 수 있게 한다.
        """
        document_titles = document_titles or {}

        context_items = [
            {
                "index": i,
                "document_id": chunk.document_id,
                "title": document_titles.get(chunk.document_id, ""),
                "text": chunk.chunk_text,
                "relevance_score": round(chunk.relevance_score, 4),
            }
            for i, chunk in enumerate(chunks)
        ]

        user_content = (
            f"질문: {question}\n\n"
            f"CONTEXT_JSON: {json.dumps(context_items, ensure_ascii=False)}\n\n"
            "위 CONTEXT_JSON의 각 항목이 검색된 과거 트러블슈팅 문서의 발췌입니다. "
            "이것만 근거로 원인/유사 사례/해결 방법을 JSON으로 답하세요."
        )

        messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
        messages.extend(history or [])
        messages.append({"role": "user", "content": user_content})
        return messages
