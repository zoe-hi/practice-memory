from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import CaptureSession
from tests.conftest import create_marker


def test_text_marker_is_saved_with_first_message(client: TestClient) -> None:
    session_id = create_marker(client)
    response = client.get(f"/api/v1/capture-sessions/{session_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "marked"
    assert body["marker_transcript"].startswith("三个孩子")
    assert body["conversation"][0]["kind"] == "marker"
    assert body["conversation"][0]["source"] == "text"
    assert "audio_temp_path" not in body


def test_create_requires_exactly_one_input(client: TestClient) -> None:
    missing = client.post("/api/v1/capture-sessions")
    assert missing.status_code == 400
    assert missing.json()["error"]["code"] == "INPUT_REQUIRED"

    both = client.post(
        "/api/v1/capture-sessions",
        data={"text": "文字"},
        files={"audio": ("marker.webm", b"audio", "audio/webm")},
    )
    assert both.status_code == 400
    assert both.json()["error"]["code"] == "INPUT_REQUIRED"


def test_list_reads_persisted_session_and_returns_preview(client: TestClient) -> None:
    session_id = create_marker(client, text="甲" * 150)
    with Session(client.app.state.engine) as independent_db:
        stored = independent_db.get(CaptureSession, session_id)
        assert stored is not None
        assert stored.status == "marked"

    response = client.get("/api/v1/capture-sessions?status=marked&limit=20")
    assert response.status_code == 200
    assert response.json()[0]["id"] == session_id
    assert response.json()[0]["marker_transcript_preview"] == "甲" * 120


def test_patch_transcript_updates_marker_message(client: TestClient) -> None:
    session_id = create_marker(client)
    response = client.patch(
        f"/api/v1/capture-sessions/{session_id}",
        json={"activity_name": "修正活动", "marker_transcript": "修正后的现场标记"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["activity_name"] == "修正活动"
    assert body["marker_transcript"] == "修正后的现场标记"
    assert body["conversation"][0]["text"] == "修正后的现场标记"


def test_direct_reflection_can_start_once(client: TestClient) -> None:
    response = client.post(
        "/api/v1/capture-sessions",
        data={"text": "活动刚结束，记录一下", "entry_mode": "direct_reflection"},
    )
    assert response.status_code == 201
    session_id = response.json()["id"]
    assert response.json()["status"] == "reflecting"

    started = client.post(
        f"/api/v1/capture-sessions/{session_id}/start-reflection"
    )
    assert started.status_code == 200
    repeated = client.post(
        f"/api/v1/capture-sessions/{session_id}/start-reflection"
    )
    assert repeated.status_code == 409
    assert repeated.json()["error"]["code"] == "INVALID_STATE"

