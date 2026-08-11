"""즐겨찾기(FR-ETC-02)/최근 본 문서(FR-ETC-03) 통합 테스트."""
import pytest

from app.models.project import Project


@pytest.fixture
def auth_headers(client):
    client.post(
        "/api/v1/auth/signup",
        json={"email": "bookmarker@example.com", "password": "password123", "nickname": "bm"},
    )
    tokens = client.post(
        "/api/v1/auth/login", json={"email": "bookmarker@example.com", "password": "password123"}
    ).json()["data"]
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture
def document_id(client, auth_headers, db_session):
    project = Project(name="북마크 테스트 프로젝트")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    response = client.post(
        "/api/v1/documents",
        json={"project_id": project.id, "title": "북마크 테스트 문서", "problem_description": "설명"},
        headers=auth_headers,
    )
    return response.json()["data"]["id"]


class TestToggleBookmark:
    def test_toggle_adds_then_removes_bookmark(self, client, auth_headers, document_id):
        first = client.post(f"/api/v1/bookmarks/{document_id}", headers=auth_headers)
        assert first.status_code == 200
        assert first.json()["data"]["bookmarked"] is True

        second = client.post(f"/api/v1/bookmarks/{document_id}", headers=auth_headers)
        assert second.json()["data"]["bookmarked"] is False

    def test_toggle_without_auth_fails(self, client, document_id):
        response = client.post(f"/api/v1/bookmarks/{document_id}")
        assert response.status_code == 401

    def test_toggle_nonexistent_document_returns_404(self, client, auth_headers):
        response = client.post("/api/v1/bookmarks/does-not-exist", headers=auth_headers)
        assert response.status_code == 404


class TestListBookmarks:
    def test_list_reflects_current_state(self, client, auth_headers, document_id):
        client.post(f"/api/v1/bookmarks/{document_id}", headers=auth_headers)

        response = client.get("/api/v1/bookmarks", headers=auth_headers)

        assert response.json()["data"] == [document_id]

    def test_list_empty_when_nothing_bookmarked(self, client, auth_headers):
        response = client.get("/api/v1/bookmarks", headers=auth_headers)
        assert response.json()["data"] == []


class TestRecentViews:
    def test_record_view_adds_to_recent_views(self, client, auth_headers, document_id):
        response = client.post(f"/api/v1/bookmarks/recent-views/{document_id}", headers=auth_headers)
        assert response.status_code == 200

        listed = client.get("/api/v1/bookmarks/recent-views", headers=auth_headers).json()["data"]
        assert listed == [document_id]

    def test_record_view_twice_does_not_duplicate(self, client, auth_headers, document_id):
        client.post(f"/api/v1/bookmarks/recent-views/{document_id}", headers=auth_headers)
        client.post(f"/api/v1/bookmarks/recent-views/{document_id}", headers=auth_headers)

        listed = client.get("/api/v1/bookmarks/recent-views", headers=auth_headers).json()["data"]
        assert listed == [document_id]

    def test_record_view_on_nonexistent_document_returns_404(self, client, auth_headers):
        response = client.post("/api/v1/bookmarks/recent-views/does-not-exist", headers=auth_headers)
        assert response.status_code == 404

    def test_record_view_without_auth_fails(self, client, document_id):
        response = client.post(f"/api/v1/bookmarks/recent-views/{document_id}")
        assert response.status_code == 401
