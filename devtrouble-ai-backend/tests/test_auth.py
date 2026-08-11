"""
인증(JWT) 기능 통합 테스트.

FR-AUTH-01~05 전체 플로우를 API 엔드포인트 기준으로 검증한다:
회원가입 → 로그인 → 보호된 리소스 접근 → 토큰 재발급(Rotation) → 로그아웃
"""


def _sign_up(client, email="user@example.com", password="password123", nickname="tester"):
    return client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": password, "nickname": nickname},
    )


def _login(client, email="user@example.com", password="password123"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


class TestSignUp:
    def test_signup_success(self, client):
        response = _sign_up(client)

        assert response.status_code == 201
        body = response.json()
        assert body["success"] is True
        assert body["data"]["email"] == "user@example.com"
        assert body["data"]["nickname"] == "tester"
        assert body["data"]["role"] == "USER"
        # 비밀번호 해시는 절대 응답에 노출되면 안 된다
        assert "password" not in body["data"]
        assert "password_hash" not in body["data"]

    def test_signup_duplicate_email_fails(self, client):
        _sign_up(client)
        response = _sign_up(client)

        assert response.status_code == 409
        body = response.json()
        assert body["success"] is False
        assert body["error"]["code"] == "DUPLICATE_RESOURCE"

    def test_signup_short_password_rejected(self, client):
        response = client.post(
            "/api/v1/auth/signup",
            json={"email": "a@example.com", "password": "short", "nickname": "a"},
        )
        assert response.status_code == 422


class TestLogin:
    def test_login_success_returns_token_pair(self, client):
        _sign_up(client)
        response = _login(client)

        assert response.status_code == 200
        body = response.json()["data"]
        assert body["access_token"]
        assert body["refresh_token"]
        assert body["token_type"] == "bearer"

    def test_login_wrong_password_fails(self, client):
        _sign_up(client)
        response = _login(client, password="wrong-password")

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHORIZED"

    def test_login_nonexistent_user_fails(self, client):
        response = _login(client, email="ghost@example.com")

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHORIZED"


class TestProtectedResource:
    def test_access_with_valid_token_succeeds(self, client):
        _sign_up(client)
        tokens = _login(client).json()["data"]

        response = client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )

        assert response.status_code == 200
        assert response.json()["data"]["email"] == "user@example.com"

    def test_access_without_token_fails(self, client):
        response = client.get("/api/v1/users/me")

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHORIZED"

    def test_access_with_malformed_header_fails(self, client):
        response = client.get(
            "/api/v1/users/me", headers={"Authorization": "NotBearer sometoken"}
        )
        assert response.status_code == 401

    def test_access_with_invalid_token_fails(self, client):
        response = client.get(
            "/api/v1/users/me", headers={"Authorization": "Bearer invalid.token.value"}
        )
        assert response.status_code == 401

    def test_access_with_refresh_token_as_access_fails(self, client):
        """Refresh Token을 Access Token 대신 사용하려는 시도는 거부되어야 한다."""
        _sign_up(client)
        tokens = _login(client).json()["data"]

        response = client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
        )
        assert response.status_code == 401


class TestRefresh:
    def test_refresh_issues_new_token_pair(self, client):
        _sign_up(client)
        tokens = _login(client).json()["data"]

        response = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )

        assert response.status_code == 200
        new_tokens = response.json()["data"]
        assert new_tokens["access_token"]
        assert new_tokens["refresh_token"] != tokens["refresh_token"]

    def test_refresh_rotation_invalidates_old_token(self, client):
        """FR-AUTH-03: 한 번 사용된 Refresh Token은 재사용할 수 없어야 한다 (Rotation)."""
        _sign_up(client)
        tokens = _login(client).json()["data"]

        first = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert first.status_code == 200

        replay = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert replay.status_code == 401
        assert replay.json()["error"]["code"] == "UNAUTHORIZED"

    def test_refresh_with_access_token_fails(self, client):
        _sign_up(client)
        tokens = _login(client).json()["data"]

        response = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]}
        )
        assert response.status_code == 401

    def test_refresh_with_garbage_token_fails(self, client):
        response = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": "garbage"}
        )
        assert response.status_code == 401


class TestLogout:
    def test_logout_revokes_refresh_token(self, client):
        _sign_up(client)
        tokens = _login(client).json()["data"]

        logout_response = client.post(
            "/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}
        )
        assert logout_response.status_code == 200

        # 로그아웃 이후에는 같은 Refresh Token으로 재발급받을 수 없어야 한다 (FR-AUTH-04)
        reuse_response = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert reuse_response.status_code == 401

    def test_logout_with_unknown_token_is_idempotent(self, client):
        """존재하지 않는 토큰으로 로그아웃해도 에러 없이 성공 처리한다."""
        response = client.post(
            "/api/v1/auth/logout", json={"refresh_token": "unknown-token"}
        )
        assert response.status_code == 200
