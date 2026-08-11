"""태그 목록 조회 및 관리자 태그 통합(FR-ETC-04) 통합 테스트."""
import pytest

from app.models.project import Project
from app.models.user import User, UserRole


@pytest.fixture
def auth_headers(client):
    client.post(
        "/api/v1/auth/signup",
        json={"email": "tagger@example.com", "password": "password123", "nickname": "tagger"},
    )
    tokens = client.post(
        "/api/v1/auth/login", json={"email": "tagger@example.com", "password": "password123"}
    ).json()["data"]
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture
def admin_headers(client, db_session):
    client.post(
        "/api/v1/auth/signup",
        json={"email": "admin@example.com", "password": "password123", "nickname": "admin"},
    )
    admin_user = db_session.query(User).filter(User.email == "admin@example.com").one()
    admin_user.role = UserRole.ADMIN
    db_session.commit()

    tokens = client.post(
        "/api/v1/auth/login", json={"email": "admin@example.com", "password": "password123"}
    ).json()["data"]
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture
def project_id(db_session):
    project = Project(name="태그 테스트 프로젝트")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project.id


def _create_document_with_tags(client, headers, project_id, tag_names):
    response = client.post(
        "/api/v1/documents",
        json={
            "project_id": project_id,
            "title": "태그 테스트 문서",
            "problem_description": "설명",
            "tag_names": tag_names,
        },
        headers=headers,
    )
    return response.json()["data"]


class TestListTags:
    def test_list_tags_returns_all_created_tags(self, client, auth_headers, project_id):
        _create_document_with_tags(client, auth_headers, project_id, ["mysql", "deadlock"])

        response = client.get("/api/v1/tags")

        assert response.status_code == 200
        names = {t["name"] for t in response.json()["data"]}
        assert {"mysql", "deadlock"}.issubset(names)

    def test_list_tags_empty_when_none_created(self, client):
        response = client.get("/api/v1/tags")
        assert response.status_code == 200
        assert response.json()["data"] == []


class TestMergeTags:
    def test_admin_can_merge_tags(self, client, auth_headers, admin_headers, project_id, db_session):
        from app.models.tag import Tag

        doc = _create_document_with_tags(client, auth_headers, project_id, ["db-error"])
        db_session.add(Tag(name="database-error"))
        db_session.commit()

        source = db_session.query(Tag).filter(Tag.name == "database-error").one()
        target = db_session.query(Tag).filter(Tag.name == "db-error").one()

        response = client.post(
            "/api/v1/admin/tags/merge",
            json={"source_tag_id": source.id, "target_tag_id": target.id},
            headers=admin_headers,
        )

        assert response.status_code == 200
        # source 태그는 삭제되어야 한다
        remaining_names = {t["name"] for t in client.get("/api/v1/tags").json()["data"]}
        assert "database-error" not in remaining_names
        assert "db-error" in remaining_names

        # 문서는 여전히 (통합된) 태그를 가지고 있어야 한다
        doc_detail = client.get(f"/api/v1/documents/{doc['id']}").json()["data"]
        assert "db-error" in doc_detail["tag_names"]

    def test_merge_reassigns_documents_without_duplicate_conflict(
        self, client, auth_headers, admin_headers, project_id, db_session
    ):
        """문서가 source/target 태그를 동시에 갖고 있어도 병합 시 충돌 없이 처리되어야 한다."""
        from app.models.tag import Tag

        doc = _create_document_with_tags(client, auth_headers, project_id, ["a-tag", "b-tag"])
        source = db_session.query(Tag).filter(Tag.name == "a-tag").one()
        target = db_session.query(Tag).filter(Tag.name == "b-tag").one()

        response = client.post(
            "/api/v1/admin/tags/merge",
            json={"source_tag_id": source.id, "target_tag_id": target.id},
            headers=admin_headers,
        )

        assert response.status_code == 200
        doc_detail = client.get(f"/api/v1/documents/{doc['id']}").json()["data"]
        assert doc_detail["tag_names"] == ["b-tag"]

    def test_non_admin_cannot_merge_tags(self, client, auth_headers, project_id, db_session):
        from app.models.tag import Tag

        _create_document_with_tags(client, auth_headers, project_id, ["x-tag", "y-tag"])
        source = db_session.query(Tag).filter(Tag.name == "x-tag").one()
        target = db_session.query(Tag).filter(Tag.name == "y-tag").one()

        response = client.post(
            "/api/v1/admin/tags/merge",
            json={"source_tag_id": source.id, "target_tag_id": target.id},
            headers=auth_headers,
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"

    def test_merge_same_tag_rejected(self, client, admin_headers, auth_headers, project_id, db_session):
        from app.models.tag import Tag

        _create_document_with_tags(client, auth_headers, project_id, ["solo-tag"])
        tag = db_session.query(Tag).filter(Tag.name == "solo-tag").one()

        response = client.post(
            "/api/v1/admin/tags/merge",
            json={"source_tag_id": tag.id, "target_tag_id": tag.id},
            headers=admin_headers,
        )

        assert response.status_code == 422

    def test_merge_nonexistent_tag_returns_404(self, client, admin_headers):
        response = client.post(
            "/api/v1/admin/tags/merge",
            json={"source_tag_id": "no-such-id", "target_tag_id": "also-no-such-id"},
            headers=admin_headers,
        )
        assert response.status_code == 404
