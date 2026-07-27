from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_reports_database_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_does_not_leak_connection_details():
    """/health is unauthenticated, so it must never echo database errors."""
    body = client.get("/health").json()

    assert "detail" not in body
    assert "postgresql" not in str(body).lower()
