import uuid

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_home_endpoint():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "message": "Welcome to InsightFlow AI"
    }


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy"
    }
    assert response.headers["X-Request-ID"]


def test_request_id_is_preserved():
    response = client.get(
        "/health/live",
        headers={"X-Request-ID": "test-request-123"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
    assert response.headers["X-Request-ID"] == "test-request-123"


def test_readiness_endpoint_checks_database():
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_unknown_endpoint_returns_not_found():
    response = client.get("/does-not-exist")

    assert response.status_code == 404


def test_legacy_dataset_routes_require_authentication():
    response = client.get(
        "/dataset-versions/unknown-file.csv"
    )

    assert response.status_code == 401
    assert client.get("/pipeline-runs").status_code == 401
    assert client.get("/quality-monitoring/unknown-file.csv").status_code == 401


def test_legacy_history_routes_hide_another_users_dataset():
    unique_id = uuid.uuid4().hex
    owner = client.post(
        "/auth/register",
        json={
            "email": f"history_owner_{unique_id}@example.com",
            "username": f"history_owner_{unique_id[:10]}",
            "password": "historypass123",
        },
    )
    other_user = client.post(
        "/auth/register",
        json={
            "email": f"history_other_{unique_id}@example.com",
            "username": f"history_other_{unique_id[:10]}",
            "password": "historypass123",
        },
    )
    owner_headers = {
        "Authorization": f"Bearer {owner.json()['access_token']}",
    }
    other_headers = {
        "Authorization": f"Bearer {other_user.json()['access_token']}",
    }
    workspace = client.post(
        "/api/workspaces",
        headers=owner_headers,
        json={"name": f"History Workspace {unique_id}"},
    ).json()
    project = client.post(
        "/api/projects",
        headers=owner_headers,
        json={
            "name": f"History Project {unique_id}",
            "workspace_id": workspace["id"],
        },
    ).json()
    filename = f"history_{unique_id}.csv"
    upload_response = client.post(
        "/upload",
        headers=owner_headers,
        data={"project_id": str(project["id"])},
        files={
            "file": (
                filename,
                b"Task_ID,Status\nHISTORY-001,Completed\n",
                "text/csv",
            )
        },
    )
    assert upload_response.status_code == 200

    assert client.get(
        f"/dataset-versions/{filename}",
        headers=other_headers,
    ).status_code == 404
    assert client.get(
        f"/quality-monitoring/{filename}",
        headers=other_headers,
    ).status_code == 404