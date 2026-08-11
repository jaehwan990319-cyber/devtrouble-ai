"""
Vector 저장/검색을 담당하는 VectorStore 계층.

RDB(document_embeddings)는 청크 원문 + vector_id를 보관하는 Source of Truth,
VectorStore는 순수 유사도 검색 인덱스라는 ERD 설계 원칙을 그대로 따른다.
VectorStore 구현체는 (vector_id: str, score: float) 쌍만 돌려주고,
청크 원문/문서 정보는 RetrieverService가 document_embeddings 테이블에서 조회한다.

- FaissVectorStore: 개발/테스트용. 프로세스 메모리 내 인덱스 (실제 동작, 네트워크 불필요).
- ChromaVectorStore: 로컬 영속 저장이 필요할 때. chromadb의 PersistentClient를 사용하며
  별도 서버 없이 디스크에 바로 저장된다 (실제 동작 확인 완료 — 아래 클래스 docstring 참고).
- QdrantVectorStore: 운영용. qdrant-client로 원격 Qdrant 서버에 연결.
"""
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core.config import Settings, get_settings


@dataclass
class VectorMatch:
    vector_id: str
    score: float


class VectorStore(ABC):
    @abstractmethod
    def upsert_batch(self, items: list[tuple[str, list[float]]]) -> None:
        """[(vector_id, embedding), ...] 를 색인에 추가/갱신한다."""
        raise NotImplementedError

    @abstractmethod
    def search(self, query_embedding: list[float], top_k: int) -> list[VectorMatch]:
        raise NotImplementedError

    @abstractmethod
    def delete(self, vector_ids: list[str]) -> None:
        raise NotImplementedError


def _vector_id_to_int(vector_id: str) -> int:
    """FAISS IndexIDMap이 요구하는 int64 ID로 문자열 vector_id를 결정론적으로 매핑."""
    digest = hashlib.blake2b(vector_id.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, byteorder="big", signed=False) & 0x7FFFFFFFFFFFFFFF


class FaissVectorStore(VectorStore):
    """
    프로세스 메모리 내에서만 동작하는 개발/테스트용 벡터 저장소.

    NOTE: 프로세스가 재시작되면 인덱스가 사라진다. 로컬 개발 편의를 위한 트레이드오프이며,
    운영 환경은 QdrantVectorStore(영속 스토리지)를 사용한다.
    """

    def __init__(self, dimension: int):
        import faiss

        self._dimension = dimension
        # 코사인 유사도를 위해 벡터를 단위 벡터로 정규화한 뒤 Inner Product로 검색한다.
        self._index = faiss.IndexIDMap(faiss.IndexFlatIP(dimension))
        self._id_to_vector_id: dict[int, str] = {}

    def upsert_batch(self, items: list[tuple[str, list[float]]]) -> None:
        if not items:
            return
        import numpy as np

        # 같은 vector_id로 재삽입될 수 있으므로(문서 재색인) 먼저 제거 후 추가한다.
        self.delete([vector_id for vector_id, _ in items])

        vectors = np.array([embedding for _, embedding in items], dtype="float32")
        vectors = self._normalize(vectors)
        int_ids = np.array([_vector_id_to_int(vector_id) for vector_id, _ in items], dtype="int64")

        self._index.add_with_ids(vectors, int_ids)
        for vector_id, int_id in zip((v for v, _ in items), int_ids, strict=True):
            self._id_to_vector_id[int(int_id)] = vector_id

    def search(self, query_embedding: list[float], top_k: int) -> list[VectorMatch]:
        if self._index.ntotal == 0:
            return []
        import numpy as np

        query = np.array([query_embedding], dtype="float32")
        query = self._normalize(query)

        scores, int_ids = self._index.search(query, min(top_k, self._index.ntotal))

        matches: list[VectorMatch] = []
        for score, int_id in zip(scores[0], int_ids[0], strict=True):
            if int_id == -1:
                continue
            vector_id = self._id_to_vector_id.get(int(int_id))
            if vector_id is not None:
                matches.append(VectorMatch(vector_id=vector_id, score=float(score)))
        return matches

    def delete(self, vector_ids: list[str]) -> None:
        if not vector_ids:
            return
        import numpy as np

        int_ids = np.array([_vector_id_to_int(v) for v in vector_ids], dtype="int64")
        self._index.remove_ids(int_ids)
        for vector_id in vector_ids:
            self._id_to_vector_id.pop(_vector_id_to_int(vector_id), None)

    @staticmethod
    def _normalize(vectors):
        import numpy as np

        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return vectors / norms


class ChromaVectorStore(VectorStore):
    """
    chromadb의 PersistentClient 기반 VectorStore.

    Qdrant처럼 별도 서버 프로세스를 띄울 필요 없이(임베디드 모드), 디스크 경로만 지정하면
    FAISS와 달리 프로세스가 재시작돼도 색인이 남아있다 — FAISS(휘발성)와 Qdrant(서버 필요)
    사이의 중간 지점. 실제로 upsert/search/delete/재시작 후 유지 여부까지 검증했다
    (tests/test_chroma_vector_store.py).

    코사인 거리(hnsw:space=cosine)로 컬렉션을 만들고, score = 1 - distance로 변환해
    FaissVectorStore/QdrantVectorStore와 동일하게 "높을수록 유사"로 통일한다.
    """

    def __init__(self, dimension: int, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.dimension = dimension
        self._client = None
        self._collection = None

    def _get_collection(self):
        if self._collection is None:
            import chromadb

            self._client = chromadb.PersistentClient(path=self.settings.CHROMA_PERSIST_DIR)
            self._collection = self._client.get_or_create_collection(
                name=self.settings.CHROMA_COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def upsert_batch(self, items: list[tuple[str, list[float]]]) -> None:
        if not items:
            return
        ids = [vector_id for vector_id, _ in items]
        embeddings = [embedding for _, embedding in items]
        # upsert이므로 이미 있는 id는 갱신되고, 없으면 새로 추가된다 (별도 delete 불필요).
        self._get_collection().upsert(ids=ids, embeddings=embeddings)

    def search(self, query_embedding: list[float], top_k: int) -> list[VectorMatch]:
        collection = self._get_collection()
        if collection.count() == 0:
            return []

        result = collection.query(
            query_embeddings=[query_embedding], n_results=min(top_k, collection.count())
        )
        ids = result["ids"][0]
        distances = result["distances"][0]
        return [VectorMatch(vector_id=vid, score=1 - dist) for vid, dist in zip(ids, distances, strict=True)]

    def delete(self, vector_ids: list[str]) -> None:
        if not vector_ids:
            return
        self._get_collection().delete(ids=vector_ids)


class QdrantVectorStore(VectorStore):
    """운영용 VectorStore. qdrant-client 기반, 컬렉션은 없으면 자동 생성한다."""

    def __init__(self, dimension: int, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.dimension = dimension
        self._client = None

    def _get_client(self):
        if self._client is None:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams

            self._client = QdrantClient(url=self.settings.QDRANT_URL)
            collections = {c.name for c in self._client.get_collections().collections}
            if self.settings.QDRANT_COLLECTION_NAME not in collections:
                self._client.create_collection(
                    collection_name=self.settings.QDRANT_COLLECTION_NAME,
                    vectors_config=VectorParams(size=self.dimension, distance=Distance.COSINE),
                )
        return self._client

    def upsert_batch(self, items: list[tuple[str, list[float]]]) -> None:
        from qdrant_client.models import PointStruct

        points = [
            PointStruct(id=_vector_id_to_int(vector_id), vector=embedding, payload={"vector_id": vector_id})
            for vector_id, embedding in items
        ]
        self._get_client().upsert(collection_name=self.settings.QDRANT_COLLECTION_NAME, points=points)

    def search(self, query_embedding: list[float], top_k: int) -> list[VectorMatch]:
        response = self._get_client().query_points(
            collection_name=self.settings.QDRANT_COLLECTION_NAME,
            query=query_embedding,
            limit=top_k,
        )
        return [VectorMatch(vector_id=p.payload["vector_id"], score=p.score) for p in response.points]

    def delete(self, vector_ids: list[str]) -> None:
        from qdrant_client.models import PointIdsList

        ids = [_vector_id_to_int(v) for v in vector_ids]
        self._get_client().delete(
            collection_name=self.settings.QDRANT_COLLECTION_NAME, points_selector=PointIdsList(points=ids)
        )


_vector_store_singleton: VectorStore | None = None


def get_vector_store(dimension: int, settings: Settings | None = None) -> VectorStore:
    """
    settings.VECTOR_DB_PROVIDER에 따라 FAISS/Chroma/Qdrant 중 하나를 선택하는 팩토리.

    FaissVectorStore는 프로세스 메모리 상태이므로 요청마다 새로 만들면 색인이
    유지되지 않는다 — 프로세스 수명 동안 하나의 인스턴스를 재사용하는 모듈 싱글턴으로 관리한다.
    """
    global _vector_store_singleton
    settings = settings or get_settings()

    if _vector_store_singleton is None:
        if settings.VECTOR_DB_PROVIDER == "qdrant":
            _vector_store_singleton = QdrantVectorStore(dimension, settings)
        elif settings.VECTOR_DB_PROVIDER == "chroma":
            _vector_store_singleton = ChromaVectorStore(dimension, settings)
        else:
            _vector_store_singleton = FaissVectorStore(dimension)
    return _vector_store_singleton


def reset_vector_store_for_testing() -> None:
    """테스트 간 격리를 위해 싱글턴을 초기화한다. 프로덕션 코드에서는 호출하지 않는다."""
    global _vector_store_singleton
    _vector_store_singleton = None
