"""
④ 하이브리드 검색 — 벡터 임베딩이 놓친 문서를 키워드(LIKE) 검색이 보완하는지 검증한다.

"벡터 검색으로는 절대 못 찾는" 시나리오를 명확히 보이려고, 벡터 스토어를
비어있는 상태로 두고(색인을 안 함) 키워드 검색만으로 찾아지는지를 확인한다 —
이렇게 하면 두 검색 경로가 실제로 독립적으로 동작한다는 것을 가장 명확하게 보여준다.
"""
import pytest

from app.models.project import Project
from app.models.trouble_document import TroubleDocument
from app.schemas.ai import AiSearchRequest
from app.services.ai.embedding_provider import LocalHashEmbeddingProvider
from app.services.ai.embedding_service import EmbeddingService
from app.services.ai.llm_client import TemplateLlmClient
from app.services.ai.prompt_builder import PromptBuilder
from app.services.ai.rag_service import RagService
from app.services.ai.retriever_service import RetrieverService
from app.services.ai.vector_store import FaissVectorStore
from tests.test_rag_reformulation import _settings


@pytest.fixture
def project_id(db_session):
    project = Project(name="하이브리드 검색 테스트 프로젝트")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project.id


def _build_rag_service(db_session):
    provider = LocalHashEmbeddingProvider()
    vector_store = FaissVectorStore(dimension=provider.dimension)
    settings = _settings()
    embedding_service = EmbeddingService(db=db_session, provider=provider, vector_store=vector_store)
    retriever_service = RetrieverService(
        db=db_session, provider=provider, vector_store=vector_store, settings=settings
    )
    rag_service = RagService(
        db=db_session,
        embedding_service=embedding_service,
        retriever_service=retriever_service,
        prompt_builder=PromptBuilder(),
        llm_client=TemplateLlmClient(),
        settings=settings,
    )
    return rag_service, embedding_service


class TestHybridSearch:
    def test_keyword_search_finds_document_not_in_vector_index(self, db_session, project_id):
        """벡터 색인은 전혀 안 됐지만, 제목에 있는 고유 에러코드로 키워드 검색만으로 찾아져야 한다."""
        document = TroubleDocument(
            project_id=project_id,
            title="ERRCODE-9981 결제 승인 실패",
            problem_description="결제 게이트웨이에서 ERRCODE-9981을 반환하며 승인이 거부된다.",
            solution="가맹점 키 만료가 원인이었다.",
        )
        db_session.add(document)
        db_session.commit()
        db_session.refresh(document)
        # 의도적으로 embedding_service.index_document()를 호출하지 않는다 — 벡터 색인 없음.

        rag_service, _ = _build_rag_service(db_session)
        response = rag_service.search(AiSearchRequest(query="ERRCODE-9981"), user_id=None)

        assert len(response.citations) == 1
        assert response.citations[0].document_id == document.id

    def test_hybrid_search_respects_project_filter(self, db_session, project_id):
        """키워드 검색도 project_id 필터를 존중해야 한다 (다른 프로젝트 문서는 안 나옴)."""
        other_project = Project(name="다른 프로젝트")
        db_session.add(other_project)
        db_session.commit()
        db_session.refresh(other_project)

        target = TroubleDocument(
            project_id=project_id,
            title="ERRCODE-7777 특수 오류",
            problem_description="설명",
        )
        other = TroubleDocument(
            project_id=other_project.id,
            title="ERRCODE-7777 특수 오류",  # 일부러 같은 제목으로 다른 프로젝트에도 생성
            problem_description="설명",
        )
        db_session.add_all([target, other])
        db_session.commit()
        db_session.refresh(target)
        db_session.refresh(other)

        rag_service, _ = _build_rag_service(db_session)
        response = rag_service.search(
            AiSearchRequest(query="ERRCODE-7777", project_id=project_id), user_id=None
        )

        doc_ids = {c.document_id for c in response.citations}
        assert doc_ids == {target.id}

    def test_no_keyword_match_and_no_vector_index_returns_no_results(self, db_session, project_id):
        """벡터 색인도 없고 키워드도 안 맞으면, 두 경로 다 실패해 안내 메시지로 끝나야 한다."""
        rag_service, _ = _build_rag_service(db_session)

        response = rag_service.search(AiSearchRequest(query="아무것도 없는 질문"), user_id=None)

        assert response.citations == []
        assert "찾지 못했습니다" in response.answer
