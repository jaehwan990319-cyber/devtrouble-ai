"""
RAG 파이프라인 1단계: 문서 Chunking + Embedding 생성 + 색인.

PRD AI 파이프라인 대응: 질문 분석 → [Embedding 생성] → Vector Search → ...
(문서 색인 시점 기준으로는 "질문 분석" 대신 "문서 저장/수정"이 트리거가 된다)

역할 분리:
- chunk_document: 순수 텍스트 분할 로직 (외부 의존성 없음)
- embed_texts: EmbeddingProvider에 위임
- index_document / remove_document: document_embeddings(RDB) + VectorStore(검색 인덱스)
  두 곳을 함께 갱신하는 오케스트레이션 (Source of Truth와 검색 인덱스를 항상 일치시킨다)
"""
import re

from sqlalchemy.orm import Session

from app.models.document_embedding import DocumentEmbedding
from app.models.trouble_document import TroubleDocument
from app.repositories.embedding_repository import EmbeddingRepository
from app.services.ai.embedding_provider import EmbeddingProvider, get_embedding_provider
from app.services.ai.vector_store import VectorStore, get_vector_store

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")

DEFAULT_MAX_CHUNK_CHARS = 800
DEFAULT_CHUNK_OVERLAP = 100


class EmbeddingService:
    def __init__(
        self,
        db: Session,
        provider: EmbeddingProvider | None = None,
        vector_store: VectorStore | None = None,
    ):
        self.db = db
        self.embedding_repo = EmbeddingRepository(db)
        self.provider = provider or get_embedding_provider()
        self.vector_store = vector_store or get_vector_store(self.provider.dimension)

    def chunk_document(
        self,
        text: str,
        max_chars: int = DEFAULT_MAX_CHUNK_CHARS,
        overlap: int = DEFAULT_CHUNK_OVERLAP,
    ) -> list[str]:
        """
        문단(빈 줄) 단위로 묶어가며 max_chars를 넘지 않는 청크를 만든다.
        하나의 문단 자체가 max_chars보다 길면 overlap을 두고 강제 분할한다
        (Stack Trace처럼 문단 구분이 없는 긴 텍스트 대비).
        """
        paragraphs = [p.strip() for p in _PARAGRAPH_SPLIT.split(text) if p.strip()]
        chunks: list[str] = []
        current = ""

        for paragraph in paragraphs:
            candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
            if len(candidate) <= max_chars:
                current = candidate
                continue

            if current:
                chunks.append(current)
                current = ""

            if len(paragraph) <= max_chars:
                current = paragraph
            else:
                chunks.extend(self._hard_split(paragraph, max_chars, overlap))

        if current:
            chunks.append(current)
        return chunks

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return self.provider.embed_texts(texts)

    def index_document(self, document_id: str) -> None:
        """문서 생성/수정 후 호출되는 색인 진입점 (Celery Task에서 사용)."""
        document = self.db.get(TroubleDocument, document_id)
        if document is None or document.deleted_at is not None:
            self.remove_document(document_id)
            return

        full_text = self._build_full_text(document)
        chunks = self.chunk_document(full_text)
        if not chunks:
            self.remove_document(document_id)
            return

        embeddings = self.embed_texts(chunks)

        # 재색인이므로 기존 청크를 먼저 정리한다 (수정 시 오래된 청크가 남지 않도록).
        self.remove_document(document_id)

        vector_items: list[tuple[str, list[float]]] = []
        records: list[DocumentEmbedding] = []
        for index, (chunk_text, embedding) in enumerate(zip(chunks, embeddings, strict=True)):
            vector_id = f"{document_id}:{index}"
            vector_items.append((vector_id, embedding))
            records.append(
                DocumentEmbedding(
                    document_id=document_id,
                    chunk_index=index,
                    chunk_text=chunk_text,
                    vector_id=vector_id,
                    embedding_model=self.provider.model_name,
                )
            )

        self.vector_store.upsert_batch(vector_items)
        for record in records:
            self.embedding_repo.add(record)
        self.db.commit()

    def remove_document(self, document_id: str) -> None:
        """문서 삭제 시 또는 재색인 직전에 기존 청크를 정리한다."""
        existing = self.embedding_repo.list_by_document(document_id)
        if not existing:
            return

        self.vector_store.delete([e.vector_id for e in existing])
        self.embedding_repo.delete_by_document(document_id)
        self.db.commit()

    # --- 내부 헬퍼 ---

    @staticmethod
    def _build_full_text(document: TroubleDocument) -> str:
        parts = [
            document.title,
            document.problem_description,
            document.error_message or "",
            document.stack_trace or "",
            document.solution or "",
            document.retrospective or "",
        ]
        return "\n\n".join(part for part in parts if part)

    @staticmethod
    def _hard_split(text: str, max_chars: int, overlap: int) -> list[str]:
        step = max(max_chars - overlap, 1)
        return [text[i : i + max_chars] for i in range(0, len(text), step)]
