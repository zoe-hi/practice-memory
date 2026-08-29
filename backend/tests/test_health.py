from fastapi.testclient import TestClient


def test_health_and_database_initialization(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    with client.app.state.engine.connect() as connection:
        assert set(client.app.state.engine.dialect.get_table_names(connection)) == {
            "capture_sessions",
            "experiences",
        }


def test_not_found_uses_unified_error(client: TestClient) -> None:
    response = client.get("/api/v1/capture-sessions/missing")
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "SESSION_NOT_FOUND",
            "message": "会话不存在。",
            "retryable": False,
        }
    }
