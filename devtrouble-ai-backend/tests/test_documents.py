"""
트러블슈팅 문서(TroubleDocument) CRUD 통합 테스트.

FR-DOC-01~04, FR-SEARCH-01~03 대응.

ProjectService는 이번 구현 범위가 아니므로, 테스트에서는
project를 API가 아닌 DB에 직접 삽입해 준비한다 (Document CRUD만 검증).
"""
import pytest

from app.models.project import Project


@pytest.fixture
def auth_headers(client):
    client.post(
        "/api/v1/auth/signup",
        json={"email": "author@example.com", "password": "password123", "nickname": "author"},
    )
    tokens = client.post(
        "/api/v1/auth/login", json={"email": "author@example.com", "password": "password123"}
    ).json()["data"]
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture
def other_auth_headers(client):
    client.post(
        "/api/v1/auth/signup",
        json={"email": "other@example.com", "password": "password123", "nickname": "other"},
    )
    tokens = client.post(
        "/api/v1/auth/login", json={"email": "other@example.com", "password": "password123"}
    ).json()["data"]
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture
def project_id(db_session):
    project = Project(name="결제 시스템 리팩토링", description="테스트 프로젝트")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project.id


def _create_document(client, headers, project_id, **overrides):
    payload = {
        "project_id": project_id,
        "title": "SQLAlchemy IntegrityError 해결",
        "problem_description": "배포 중 IntegrityError가 발생했다.",
        "error_message": "IntegrityError: (1062, Duplicate entry)",
        "stack_trace": "Traceback ...",
        "solution": "unique 제약을 확인하고 중복 데이터를 정리했다.",
        "retrospective": "마이그레이션 전 데이터 검증이 필요했다.",
        "tag_names": ["sqlalchemy", "mysql"],
    }
    payload.update(overrides)
    return client.post("/api/v1/documents", json=payload, headers=headers)


class TestCreateDocument:
    def test_create_document_success(self, client, auth_headers, project_id):
        response = _create_document(client, auth_headers, project_id)

        assert response.status_code == 201
        body = response.json()["data"]
        assert body["title"] == "SQLAlchemy IntegrityError 해결"
        assert body["project_id"] == project_id
        assert set(body["tag_names"]) == {"sqlalchemy", "mysql"}
        assert body["view_count"] == 0

    def test_create_document_without_auth_fails(self, client, project_id):
        response = _create_document(client, {}, project_id)
        assert response.status_code == 401

    def test_create_document_on_missing_project_fails(self, client, auth_headers):
        response = _create_document(client, auth_headers, "non-existent-project-id")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"

    def test_create_document_reuses_existing_tag(self, client, auth_headers, project_id, db_session):
        from app.models.tag import Tag

        _create_document(client, auth_headers, project_id, tag_names=["sqlalchemy"])
        _create_document(client, auth_headers, project_id, tag_names=["sqlalchemy"])

        tags = db_session.query(Tag).filter(Tag.name == "sqlalchemy").all()
        assert len(tags) == 1  # get_or_create로 중복 생성되지 않아야 한다


class TestGetDocument:
    def test_get_document_increments_view_count(self, client, auth_headers, project_id):
        document_id = _create_document(client, auth_headers, project_id).json()["data"]["id"]

        first = client.get(f"/api/v1/documents/{document_id}")
        second = client.get(f"/api/v1/documents/{document_id}")

        assert first.json()["data"]["view_count"] == 1
        assert second.json()["data"]["view_count"] == 2

    def test_get_nonexistent_document_returns_404(self, client):
        response = client.get("/api/v1/documents/does-not-exist")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"

    def test_get_deleted_document_returns_404(self, client, auth_headers, project_id):
        document_id = _create_document(client, auth_headers, project_id).json()["data"]["id"]
        client.delete(f"/api/v1/documents/{document_id}", headers=auth_headers)

        response = client.get(f"/api/v1/documents/{document_id}")
        assert response.status_code == 404


class TestUpdateDocument:
    def test_author_can_update_document(self, client, auth_headers, project_id):
        document_id = _create_document(client, auth_headers, project_id).json()["data"]["id"]

        response = client.patch(
            f"/api/v1/documents/{document_id}",
            json={"title": "수정된 제목", "tag_names": ["mysql", "deadlock"]},
            headers=auth_headers,
        )

        assert response.status_code == 200
        body = response.json()["data"]
        assert body["title"] == "수정된 제목"
        assert set(body["tag_names"]) == {"mysql", "deadlock"}
        # 명시하지 않은 필드는 그대로 유지되어야 한다
        assert body["problem_description"] == "배포 중 IntegrityError가 발생했다."

    def test_non_author_cannot_update_document(self, client, auth_headers, other_auth_headers, project_id):
        document_id = _create_document(client, auth_headers, project_id).json()["data"]["id"]

        response = client.patch(
            f"/api/v1/documents/{document_id}",
            json={"title": "몰래 수정 시도"},
            headers=other_auth_headers,
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"

    def test_update_nonexistent_document_returns_404(self, client, auth_headers):
        response = client.patch(
            "/api/v1/documents/does-not-exist", json={"title": "x"}, headers=auth_headers
        )
        assert response.status_code == 404


class TestDeleteDocument:
    def test_author_can_delete_document(self, client, auth_headers, project_id):
        document_id = _create_document(client, auth_headers, project_id).json()["data"]["id"]

        response = client.delete(f"/api/v1/documents/{document_id}", headers=auth_headers)
        assert response.status_code == 200

        get_response = client.get(f"/api/v1/documents/{document_id}")
        assert get_response.status_code == 404

    def test_non_author_cannot_delete_document(self, client, auth_headers, other_auth_headers, project_id):
        document_id = _create_document(client, auth_headers, project_id).json()["data"]["id"]

        response = client.delete(f"/api/v1/documents/{document_id}", headers=other_auth_headers)
        assert response.status_code == 403


class TestSearchDocuments:
    def test_search_by_keyword_matches_title(self, client, auth_headers, project_id):
        _create_document(client, auth_headers, project_id, title="Redis 커넥션 끊김 현상")
        _create_document(client, auth_headers, project_id, title="Kafka Consumer Lag 문제")

        response = client.get("/api/v1/documents", params={"keyword": "Redis"})

        assert response.status_code == 200
        results = response.json()["data"]
        assert len(results) == 1
        assert "Redis" in results[0]["title"]

    def test_search_by_tag(self, client, auth_headers, project_id):
        _create_document(client, auth_headers, project_id, title="문서 A", tag_names=["redis"])
        _create_document(client, auth_headers, project_id, title="문서 B", tag_names=["kafka"])

        response = client.get("/api/v1/documents", params={"tag": "redis"})

        results = response.json()["data"]
        assert len(results) == 1
        assert results[0]["title"] == "문서 A"

    def test_search_by_error_code(self, client, auth_headers, project_id):
        _create_document(
            client, auth_headers, project_id, title="문서 A", error_message="ECONNREFUSED"
        )
        _create_document(
            client, auth_headers, project_id, title="문서 B", error_message="ETIMEDOUT"
        )

        response = client.get("/api/v1/documents", params={"error_code": "ECONNREFUSED"})

        results = response.json()["data"]
        assert len(results) == 1
        assert results[0]["title"] == "문서 A"

    def test_search_excludes_deleted_documents(self, client, auth_headers, project_id):
        document_id = _create_document(
            client, auth_headers, project_id, title="삭제될 문서"
        ).json()["data"]["id"]
        client.delete(f"/api/v1/documents/{document_id}", headers=auth_headers)

        response = client.get("/api/v1/documents", params={"keyword": "삭제될"})

        assert response.json()["data"] == []

    def test_search_scoped_by_project(self, client, auth_headers, project_id, db_session):
        other_project = Project(name="다른 프로젝트")
        db_session.add(other_project)
        db_session.commit()
        db_session.refresh(other_project)

        _create_document(client, auth_headers, project_id, title="프로젝트1 문서")
        _create_document(client, auth_headers, other_project.id, title="프로젝트2 문서")

        response = client.get("/api/v1/documents", params={"project_id": project_id})

        results = response.json()["data"]
        assert len(results) == 1
        assert results[0]["title"] == "프로젝트1 문서"
