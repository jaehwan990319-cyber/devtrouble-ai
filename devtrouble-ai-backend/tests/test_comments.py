"""댓글(Comment) 통합 테스트. FR-ETC-01 대응."""
import pytest

from app.models.project import Project


@pytest.fixture
def auth_headers(client):
    client.post(
        "/api/v1/auth/signup",
        json={"email": "commenter@example.com", "password": "password123", "nickname": "commenter"},
    )
    tokens = client.post(
        "/api/v1/auth/login", json={"email": "commenter@example.com", "password": "password123"}
    ).json()["data"]
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture
def other_auth_headers(client):
    client.post(
        "/api/v1/auth/signup",
        json={"email": "other-commenter@example.com", "password": "password123", "nickname": "other"},
    )
    tokens = client.post(
        "/api/v1/auth/login",
        json={"email": "other-commenter@example.com", "password": "password123"},
    ).json()["data"]
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture
def document_id(client, auth_headers, db_session):
    project = Project(name="댓글 테스트 프로젝트")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    response = client.post(
        "/api/v1/documents",
        json={"project_id": project.id, "title": "댓글 테스트 문서", "problem_description": "설명"},
        headers=auth_headers,
    )
    return response.json()["data"]["id"]


class TestAddComment:
    def test_add_comment_success(self, client, auth_headers, document_id):
        response = client.post(
            f"/api/v1/documents/{document_id}/comments",
            json={"content": "저도 같은 문제 겪었어요"},
            headers=auth_headers,
        )

        assert response.status_code == 201
        body = response.json()["data"]
        assert body["content"] == "저도 같은 문제 겪었어요"
        assert body["document_id"] == document_id

    def test_add_comment_without_auth_fails(self, client, document_id):
        response = client.post(
            f"/api/v1/documents/{document_id}/comments", json={"content": "댓글"}
        )
        assert response.status_code == 401

    def test_add_comment_on_nonexistent_document_returns_404(self, client, auth_headers):
        response = client.post(
            "/api/v1/documents/does-not-exist/comments",
            json={"content": "댓글"},
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_add_empty_comment_rejected(self, client, auth_headers, document_id):
        response = client.post(
            f"/api/v1/documents/{document_id}/comments", json={"content": ""}, headers=auth_headers
        )
        assert response.status_code == 422


class TestListComments:
    def test_list_comments_in_creation_order(self, client, auth_headers, document_id):
        client.post(
            f"/api/v1/documents/{document_id}/comments", json={"content": "첫 댓글"}, headers=auth_headers
        )
        client.post(
            f"/api/v1/documents/{document_id}/comments", json={"content": "두번째 댓글"}, headers=auth_headers
        )

        response = client.get(f"/api/v1/documents/{document_id}/comments")

        contents = [c["content"] for c in response.json()["data"]]
        assert contents == ["첫 댓글", "두번째 댓글"]

    def test_list_comments_empty(self, client, document_id):
        response = client.get(f"/api/v1/documents/{document_id}/comments")
        assert response.json()["data"] == []


class TestDeleteComment:
    def test_author_can_delete_own_comment(self, client, auth_headers, document_id):
        comment_id = client.post(
            f"/api/v1/documents/{document_id}/comments", json={"content": "삭제될 댓글"}, headers=auth_headers
        ).json()["data"]["id"]

        response = client.delete(
            f"/api/v1/documents/{document_id}/comments/{comment_id}", headers=auth_headers
        )
        assert response.status_code == 200

        remaining = client.get(f"/api/v1/documents/{document_id}/comments").json()["data"]
        assert remaining == []

    def test_non_author_cannot_delete_comment(self, client, auth_headers, other_auth_headers, document_id):
        comment_id = client.post(
            f"/api/v1/documents/{document_id}/comments", json={"content": "댓글"}, headers=auth_headers
        ).json()["data"]["id"]

        response = client.delete(
            f"/api/v1/documents/{document_id}/comments/{comment_id}", headers=other_auth_headers
        )
        assert response.status_code == 403

    def test_delete_nonexistent_comment_returns_404(self, client, auth_headers, document_id):
        response = client.delete(
            f"/api/v1/documents/{document_id}/comments/does-not-exist", headers=auth_headers
        )
        assert response.status_code == 404
