from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        audio_storage_dir=str(tmp_path / "audio"),
        ai_provider="fake",
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings=settings)) as test_client:
        yield test_client


def create_marker(
    client: TestClient,
    text: str = "三个孩子一直站在门口，我先改成自由选书",
    activity_name: str = "亲子共读活动",
) -> str:
    response = client.post(
        "/api/v1/capture-sessions",
        data={"text": text, "activity_name": activity_name},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def advance_to_draft(client: TestClient, session_id: str) -> dict:
    response = client.post(
        f"/api/v1/capture-sessions/{session_id}/start-reflection"
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "reflecting"

    response = client.post(
        f"/api/v1/capture-sessions/{session_id}/turns",
        data={"text": "孩子进来了，但现场变得比较分散。"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "reflecting"

    response = client.post(
        f"/api/v1/capture-sessions/{session_id}/turns",
        data={"text": "降低参与门槛做得好，但现场分散是不足；下次要提前准备收拢方法。"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "reflecting"

    response = client.post(
        f"/api/v1/capture-sessions/{session_id}/turns",
        data={"text": "下次要提前准备收拢方法；暂时不确定自由选书是否适合人数更多的活动。"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "needs_confirmation"
    return response.json()

