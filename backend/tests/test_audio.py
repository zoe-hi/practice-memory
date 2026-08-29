from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.ai import FakeAIProvider
from app.main import create_app
from app.models import CaptureSession
from app.services import transcribe_initial_marker
from tests.conftest import advance_to_draft, create_marker


ALLOWED_AUDIO_TYPES = [
    ("audio/webm", ".webm"),
    ("audio/mp4", ".mp4"),
    ("audio/x-m4a", ".m4a"),
    ("audio/mpeg", ".mp3"),
    ("audio/wav", ".wav"),
]
GOLDEN_TRANSCRIPT = "三个孩子一直站在门口，我先改成自由选书"


@pytest.mark.parametrize(("content_type", "suffix"), ALLOWED_AUDIO_TYPES)
def test_initial_audio_is_safely_stored_and_transcribed(
    settings, content_type: str, suffix: str
) -> None:
    app = create_app(
        settings=settings,
        ai_provider=FakeAIProvider(transcription_text=GOLDEN_TRANSCRIPT),
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/capture-sessions",
            data={"activity_name": "亲子共读活动"},
            files={"audio": ("../../unsafe-name.bin", b"fake audio", content_type)},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["marker_transcript"] is None
        assert "audio_temp_path" not in body
        assert str(settings.audio_storage_dir) not in response.text

        factory = client.app.state.session_factory
        with factory() as db:
            session = db.get(CaptureSession, body["id"])
            assert session is not None
            stored_path = Path(session.audio_temp_path)
            assert stored_path.is_file()
            assert stored_path.suffix == suffix
            UUID(stored_path.stem)
            assert stored_path.parent.name == session.id
            assert session.marker_transcript == GOLDEN_TRANSCRIPT
            assert session.conversation_json[0]["source"] == "audio"

        detail = client.get(f"/api/v1/capture-sessions/{body['id']}")
        assert detail.status_code == 200
        assert "audio_temp_path" not in detail.text


def test_audio_type_and_size_validation_leave_no_files(settings) -> None:
    limited = settings.model_copy(update={"max_audio_bytes": 4})
    with TestClient(create_app(settings=limited)) as client:
        unsupported = client.post(
            "/api/v1/capture-sessions",
            files={"audio": ("marker.txt", b"audio", "text/plain")},
        )
        assert unsupported.status_code == 400
        assert unsupported.json()["error"]["code"] == "UNSUPPORTED_AUDIO_TYPE"

        oversized = client.post(
            "/api/v1/capture-sessions",
            files={"audio": ("marker.wav", b"12345", "audio/wav")},
        )
        assert oversized.status_code == 400
        assert oversized.json()["error"]["code"] == "AUDIO_TOO_LARGE"
        assert not [path for path in Path(limited.audio_storage_dir).rglob("*") if path.is_file()]


def test_background_failure_is_persisted_and_start_reflection_retries(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/v1/capture-sessions",
        data={"activity_name": "活动"},
        files={"audio": ("marker.webm", b"audio", "audio/webm")},
    )
    assert created.status_code == 201
    session_id = created.json()["id"]

    factory = client.app.state.session_factory
    with factory() as db:
        session = db.get(CaptureSession, session_id)
        assert session is not None
        audio_path = Path(session.audio_temp_path)
        assert audio_path.is_file()
        assert session.status == "marked"
        assert session.marker_transcript is None
        assert session.error_code == "TRANSCRIPTION_FAILED"

    failed = client.post(
        f"/api/v1/capture-sessions/{session_id}/start-reflection"
    )
    assert failed.status_code == 502
    assert failed.json()["error"] == {
        "code": "TRANSCRIPTION_FAILED",
        "message": "音频转写失败，请重试。",
        "retryable": True,
    }
    assert audio_path.is_file()

    client.app.state.ai_provider = FakeAIProvider(
        transcription_text="同步重试得到的转写"
    )
    retried = client.post(
        f"/api/v1/capture-sessions/{session_id}/start-reflection"
    )
    assert retried.status_code == 200
    assert retried.json()["status"] == "reflecting"
    detail = client.get(f"/api/v1/capture-sessions/{session_id}").json()
    assert detail["marker_transcript"] == "同步重试得到的转写"
    assert detail["conversation"][0]["source"] == "audio"


def test_background_transcription_never_overwrites_manual_correction(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/v1/capture-sessions",
        files={"audio": ("marker.wav", b"audio", "audio/wav")},
    )
    session_id = created.json()["id"]
    corrected = client.patch(
        f"/api/v1/capture-sessions/{session_id}",
        json={"marker_transcript": "贡献者手动修正的内容"},
    )
    assert corrected.status_code == 200

    transcribe_initial_marker(
        client.app.state.session_factory,
        FakeAIProvider(transcription_text="迟到的后台转写"),
        client.app.state.audio_storage,
        session_id,
    )
    detail = client.get(f"/api/v1/capture-sessions/{session_id}").json()
    assert detail["marker_transcript"] == "贡献者手动修正的内容"
    assert detail["conversation"][0]["source"] == "text"


def test_missing_initial_audio_marks_session_failed(client: TestClient) -> None:
    created = client.post(
        "/api/v1/capture-sessions",
        files={"audio": ("marker.wav", b"audio", "audio/wav")},
    )
    session_id = created.json()["id"]
    factory = client.app.state.session_factory
    with factory() as db:
        session = db.get(CaptureSession, session_id)
        audio_path = Path(session.audio_temp_path)
    audio_path.unlink()

    response = client.post(
        f"/api/v1/capture-sessions/{session_id}/start-reflection"
    )
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "STORAGE_ERROR"
    with factory() as db:
        session = db.get(CaptureSession, session_id)
        assert session.status == "failed"


def test_audio_answer_is_transcribed_and_immediately_deleted(settings) -> None:
    provider = FakeAIProvider(transcription_text="孩子后来进入了活动")
    with TestClient(create_app(settings=settings, ai_provider=provider)) as client:
        session_id = create_marker(client)
        started = client.post(
            f"/api/v1/capture-sessions/{session_id}/start-reflection"
        )
        assert started.status_code == 200

        response = client.post(
            f"/api/v1/capture-sessions/{session_id}/turns",
            files={"audio": ("answer.m4a", b"answer", "audio/x-m4a")},
        )
        assert response.status_code == 200
        assert response.json()["answer_transcript"] == "孩子后来进入了活动"
        detail = client.get(f"/api/v1/capture-sessions/{session_id}").json()
        assert detail["conversation"][-2]["kind"] == "answer"
        assert detail["conversation"][-2]["source"] == "audio"
        assert not [
            path
            for path in Path(settings.audio_storage_dir).rglob("*")
            if path.is_file()
        ]


def test_failed_audio_answer_is_deleted_and_can_be_reuploaded(
    client: TestClient,
) -> None:
    session_id = create_marker(client)
    client.post(f"/api/v1/capture-sessions/{session_id}/start-reflection")
    failed = client.post(
        f"/api/v1/capture-sessions/{session_id}/turns",
        files={"audio": ("answer.webm", b"answer", "audio/webm")},
    )
    assert failed.status_code == 502
    assert failed.json()["error"]["retryable"] is True
    assert not [
        path
        for path in Path(client.app.state.settings.audio_storage_dir).rglob("*")
        if path.is_file()
    ]

    client.app.state.ai_provider = FakeAIProvider(transcription_text="重新上传的回答")
    retried = client.post(
        f"/api/v1/capture-sessions/{session_id}/turns",
        files={"audio": ("answer.webm", b"answer", "audio/webm")},
    )
    assert retried.status_code == 200
    assert retried.json()["answer_transcript"] == "重新上传的回答"


def test_confirmation_cleans_initial_audio(settings) -> None:
    provider = FakeAIProvider(transcription_text=GOLDEN_TRANSCRIPT)
    with TestClient(create_app(settings=settings, ai_provider=provider)) as client:
        created = client.post(
            "/api/v1/capture-sessions",
            data={"activity_name": "亲子共读活动"},
            files={"audio": ("marker.webm", b"audio", "audio/webm")},
        )
        session_id = created.json()["id"]
        factory = client.app.state.session_factory
        with factory() as db:
            session = db.get(CaptureSession, session_id)
            initial_path = Path(session.audio_temp_path)
        assert initial_path.is_file()

        advance_to_draft(client, session_id)
        confirmed = client.post(
            f"/api/v1/capture-sessions/{session_id}/confirm",
            json={"contributor_name": "演示贡献者"},
        )
        assert confirmed.status_code == 201
        assert not initial_path.parent.exists()
        with factory() as db:
            session = db.get(CaptureSession, session_id)
            assert session.audio_temp_path is None

