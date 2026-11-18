import uuid

import pytest
from fastapi.testclient import TestClient

from app.auth import clear_auth_rate_limits, verify_token
from app.config.settings import settings
from app.database.connection import SessionLocal
from app.database.models import AuditEvent, User
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_auth_limits():
    clear_auth_rate_limits()
    yield
    clear_auth_rate_limits()


def test_password_reset_is_single_use_and_revokes_sessions():
    clear_auth_rate_limits()
    email = f"reset_{uuid.uuid4().hex}@example.com"

    register_response = client.post(
        "/auth/register",
        json={
            "email": email,
            "username": f"reset_{uuid.uuid4().hex[:8]}",
            "password": "oldpassword123",
        },
    )
    assert register_response.status_code == 200
    old_refresh_token = register_response.json()["refresh_token"]

    request_response = client.post(
        "/auth/password-reset/request",
        json={"email": email},
    )
    assert request_response.status_code == 200
    reset_token = request_response.json().get("reset_token")
    assert reset_token

    confirm_response = client.post(
        "/auth/password-reset/confirm",
        json={
            "reset_token": reset_token,
            "new_password": "newpassword123",
        },
    )
    assert confirm_response.status_code == 200

    assert client.post(
        "/auth/login",
        json={"email": email, "password": "oldpassword123"},
    ).status_code == 401
    assert client.post(
        "/auth/login",
        json={"email": email, "password": "newpassword123"},
    ).status_code == 200
    assert client.post(
        "/auth/refresh",
        json={"refresh_token": old_refresh_token},
    ).status_code == 401
    assert client.post(
        "/auth/password-reset/confirm",
        json={
            "reset_token": reset_token,
            "new_password": "anotherpassword123",
        },
    ).status_code == 400


def test_password_reset_request_does_not_reveal_email_exists():
    clear_auth_rate_limits()
    known_email = f"known_{uuid.uuid4().hex}@example.com"
    client.post(
        "/auth/register",
        json={
            "email": known_email,
            "username": f"known_{uuid.uuid4().hex[:8]}",
            "password": "knownpassword123",
        },
    )

    known_response = client.post(
        "/auth/password-reset/request",
        json={"email": known_email},
    )
    unknown_response = client.post(
        "/auth/password-reset/request",
        json={"email": f"unknown_{uuid.uuid4().hex}@example.com"},
    )

    assert known_response.status_code == 200
    assert unknown_response.status_code == 200
    assert known_response.json()["message"] == unknown_response.json()["message"]


def test_login_rate_limit_returns_too_many_requests():
    clear_auth_rate_limits()
    original_limit = settings.auth_rate_limit_requests
    original_window = settings.auth_rate_limit_window_seconds
    object.__setattr__(settings, "auth_rate_limit_requests", 10)
    object.__setattr__(settings, "auth_rate_limit_window_seconds", 60)
    for _ in range(10):
        response = client.post(
            "/auth/login",
            json={"email": "nobody@example.com", "password": "wrongpass"},
        )
        assert response.status_code == 401

    limited_response = client.post(
        "/auth/login",
        json={"email": "nobody@example.com", "password": "wrongpass"},
    )
    assert limited_response.status_code == 429
    object.__setattr__(settings, "auth_rate_limit_requests", original_limit)
    object.__setattr__(settings, "auth_rate_limit_window_seconds", original_window)


def test_register_and_login_user():
    email = f"user_{uuid.uuid4().hex}@example.com"
    username = f"user_{uuid.uuid4().hex[:8]}"

    register_response = client.post(
        "/auth/register",
        json={
            "email": email,
            "username": username,
            "password": "secret123",
            "role": "viewer",
        },
    )

    assert register_response.status_code == 200
    assert register_response.json()["user"]["role"] == "viewer"
    token = register_response.json()["access_token"]
    assert token

    login_response = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "secret123",
        },
    )

    assert login_response.status_code == 200
    assert login_response.json()["user"]["email"] == email

    token_payload = verify_token(login_response.json()["access_token"])
    assert token_payload["typ"] == "access"
    assert token_payload["iss"]
    assert token_payload["aud"]

    session = SessionLocal()
    try:
        assert (
            session.query(AuditEvent)
            .filter(
                AuditEvent.action == "auth.login",
                AuditEvent.outcome == "success",
            )
            .count()
            >= 1
        )
    finally:
        session.close()


def test_refresh_token_rotates_and_old_token_is_rejected():
    email = f"refresh_{uuid.uuid4().hex}@example.com"
    username = f"refresh_{uuid.uuid4().hex[:8]}"

    register_response = client.post(
        "/auth/register",
        json={
            "email": email,
            "username": username,
            "password": "refreshpass",
            "role": "viewer",
        },
    )
    first_refresh_token = register_response.json()["refresh_token"]

    refresh_response = client.post(
        "/auth/refresh",
        json={"refresh_token": first_refresh_token},
    )

    assert refresh_response.status_code == 200
    second_refresh_token = refresh_response.json()["refresh_token"]
    assert second_refresh_token != first_refresh_token

    reused_response = client.post(
        "/auth/refresh",
        json={"refresh_token": first_refresh_token},
    )
    assert reused_response.status_code == 401

    revoked_replacement_response = client.post(
        "/auth/refresh",
        json={"refresh_token": second_refresh_token},
    )
    assert revoked_replacement_response.status_code == 401


def test_logout_revokes_refresh_token():
    email = f"logout_{uuid.uuid4().hex}@example.com"
    username = f"logout_{uuid.uuid4().hex[:8]}"

    register_response = client.post(
        "/auth/register",
        json={
            "email": email,
            "username": username,
            "password": "logoutpass",
            "role": "viewer",
        },
    )
    refresh_token = register_response.json()["refresh_token"]

    logout_response = client.post(
        "/auth/logout",
        json={"refresh_token": refresh_token},
    )

    assert logout_response.status_code == 204
    assert client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token},
    ).status_code == 401


def test_admin_route_requires_admin_role():
    email = f"admin_{uuid.uuid4().hex}@example.com"
    username = f"admin_{uuid.uuid4().hex[:8]}"

    register_response = client.post(
        "/auth/register",
        json={
            "email": email,
            "username": username,
            "password": "adminpass",
            "role": "admin",
        },
    )

    assert register_response.status_code == 200
    assert register_response.json()["user"]["role"] == "viewer"
    token = register_response.json()["access_token"]

    session = SessionLocal()
    try:
        user = session.query(User).filter(User.email == email).one()
        user.role = "admin"
        session.commit()
    finally:
        session.close()

    allowed_response = client.get(
        "/admin/users",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert allowed_response.status_code == 200
    assert isinstance(allowed_response.json(), list)

    viewer_email = f"viewer_{uuid.uuid4().hex}@example.com"
    viewer_username = f"viewer_{uuid.uuid4().hex[:8]}"
    viewer_response = client.post(
        "/auth/register",
        json={
            "email": viewer_email,
            "username": viewer_username,
            "password": "viewerpass",
            "role": "viewer",
        },
    )
    viewer_token = viewer_response.json()["access_token"]

    forbidden_response = client.get(
        "/admin/users",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )

    assert forbidden_response.status_code == 403

    promoted_response = client.patch(
        f"/admin/users/{viewer_response.json()['user']['id']}/role",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "analyst"},
    )
    assert promoted_response.status_code == 200
    assert promoted_response.json()["role"] == "analyst"
