"""
프로젝트(Project) CRUD 통합 테스트. FR-PROJ-01/02 대응.
"""
import pytest


@pytest.fixture
def auth_headers(client):
    client.post(
        "/api/v1/auth/signup",
        json={"email": "owner@example.com", "password": "password123", "nickname": "owner"},
    )
    tokens = client.post(
        "/api/v1/auth/login", json={"email": "owner@example.com", "password": "password123"}
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


def _create_project(client, headers, **overrides):
    payload = {"name": "결제 시스템 리팩토링", "description": "결제 모듈 정리 프로젝트"}
    payload.update(overrides)
    return client.post("/api/v1/projects", json=payload, headers=headers)


class TestCreateProject:
    def test_create_project_success(self, client, auth_headers):
        response = _create_project(client, auth_headers)

        assert response.status_code == 201
        body = response.json()["data"]
        assert body["name"] == "결제 시스템 리팩토링"
        assert body["description"] == "결제 모듈 정리 프로젝트"
        assert body["owner_id"] is not None

    def test_create_project_without_auth_fails(self, client):
        response = _create_project(client, {})
        assert response.status_code == 401

    def test_create_project_without_description(self, client, auth_headers):
        response = _create_project(client, auth_headers, description=None)
        assert response.status_code == 201
        assert response.json()["data"]["description"] is None

    def test_create_project_blank_name_rejected(self, client, auth_headers):
        response = _create_project(client, auth_headers, name="")
        assert response.status_code == 422


class TestGetProject:
    def test_get_project_success(self, client, auth_headers):
        project_id = _create_project(client, auth_headers).json()["data"]["id"]

        response = client.get(f"/api/v1/projects/{project_id}")

        assert response.status_code == 200
        assert response.json()["data"]["id"] == project_id

    def test_get_project_visible_to_non_owner(self, client, auth_headers, other_auth_headers):
        """조회는 소유자가 아니어도 가능하다 (팀 공유 전제, 수정/삭제만 소유자 제한)."""
        project_id = _create_project(client, auth_headers).json()["data"]["id"]

        response = client.get(f"/api/v1/projects/{project_id}")
        assert response.status_code == 200

    def test_get_nonexistent_project_returns_404(self, client):
        response = client.get("/api/v1/projects/does-not-exist")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"

    def test_get_deleted_project_returns_404(self, client, auth_headers):
        project_id = _create_project(client, auth_headers).json()["data"]["id"]
        client.delete(f"/api/v1/projects/{project_id}", headers=auth_headers)

        response = client.get(f"/api/v1/projects/{project_id}")
        assert response.status_code == 404


class TestListMyProjects:
    def test_list_only_returns_own_projects(self, client, auth_headers, other_auth_headers):
        _create_project(client, auth_headers, name="내 프로젝트 A")
        _create_project(client, auth_headers, name="내 프로젝트 B")
        _create_project(client, other_auth_headers, name="남의 프로젝트")

        response = client.get("/api/v1/projects", headers=auth_headers)

        names = {p["name"] for p in response.json()["data"]}
        assert names == {"내 프로젝트 A", "내 프로젝트 B"}

    def test_list_excludes_deleted_projects(self, client, auth_headers):
        project_id = _create_project(client, auth_headers).json()["data"]["id"]
        client.delete(f"/api/v1/projects/{project_id}", headers=auth_headers)

        response = client.get("/api/v1/projects", headers=auth_headers)

        assert response.json()["data"] == []

    def test_list_without_auth_fails(self, client):
        response = client.get("/api/v1/projects")
        assert response.status_code == 401


class TestUpdateProject:
    def test_owner_can_update_project(self, client, auth_headers):
        project_id = _create_project(client, auth_headers).json()["data"]["id"]

        response = client.patch(
            f"/api/v1/projects/{project_id}",
            json={"name": "수정된 이름"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        body = response.json()["data"]
        assert body["name"] == "수정된 이름"
        # 명시하지 않은 필드는 유지되어야 한다
        assert body["description"] == "결제 모듈 정리 프로젝트"

    def test_non_owner_cannot_update_project(self, client, auth_headers, other_auth_headers):
        project_id = _create_project(client, auth_headers).json()["data"]["id"]

        response = client.patch(
            f"/api/v1/projects/{project_id}",
            json={"name": "몰래 수정 시도"},
            headers=other_auth_headers,
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"

    def test_update_nonexistent_project_returns_404(self, client, auth_headers):
        response = client.patch(
            "/api/v1/projects/does-not-exist", json={"name": "x"}, headers=auth_headers
        )
        assert response.status_code == 404


class TestDeleteProject:
    def test_owner_can_delete_project(self, client, auth_headers):
        project_id = _create_project(client, auth_headers).json()["data"]["id"]

        response = client.delete(f"/api/v1/projects/{project_id}", headers=auth_headers)
        assert response.status_code == 200

        get_response = client.get(f"/api/v1/projects/{project_id}")
        assert get_response.status_code == 404

    def test_non_owner_cannot_delete_project(self, client, auth_headers, other_auth_headers):
        project_id = _create_project(client, auth_headers).json()["data"]["id"]

        response = client.delete(f"/api/v1/projects/{project_id}", headers=other_auth_headers)
        assert response.status_code == 403


class TestProjectDocumentIntegration:
    """ProjectService 구현 이후, 이제 API만으로 프로젝트 생성 → 문서 생성까지 엔드투엔드가 가능해야 한다."""

    def test_can_create_document_in_freshly_created_project(self, client, auth_headers):
        project_id = _create_project(client, auth_headers).json()["data"]["id"]

        response = client.post(
            "/api/v1/documents",
            json={
                "project_id": project_id,
                "title": "테스트 문서",
                "problem_description": "설명",
            },
            headers=auth_headers,
        )

        assert response.status_code == 201
        assert response.json()["data"]["project_id"] == project_id
