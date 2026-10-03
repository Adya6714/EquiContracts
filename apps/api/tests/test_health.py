from fastapi.testclient import TestClient

from apps.api.app.main import app


def test_health_and_request_id() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-request-id"]
