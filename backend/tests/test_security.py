from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.audio import AudioStorage
from app.core.config import Settings
from app.core.logging import LOGGER_NAME
from app.db.base import Base
from app.db.session import build_engine, build_session_factory
from app.main import create_app
from app.models import CaptureSession


@pytest.mark.parametrize(
    "origins",
    [
        "",
        "*,http://localhost:5173",
        "ftp://localhost:5173",
        "http://user:password@localhost:5173",
        "http://localhost:5173/path",
        "http://localhost:5173?query=value",
        "http://localhost:5173#fragment",
    ],
)
def test_cors_configuration_rejects_invalid_origins(origins: str) -> None:
    with pytest.raises(ValidationError):
        Settings(cors_origins=origins)


def test_production_configuration_rejects_wildcard_origin() -> None:
    with pytest.raises(ValidationError):
        Settings(app_env="production", cors_origins="*")


def test_configuration_rejects_invalid_log_level() -> None:
    with pytest.raises(ValidationError):
        Settings(log_level="verbose")


def test_cors_preflight_allows_only_configured_origin_and_contract(settings) -> None:
    settings.cors_origins = "https://frontend.example"
    with TestClient(create_app(settings=settings)) as client:
        response = client.options(
            "/api/v1/health",
            headers={
                "Origin": "https://frontend.example",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://frontend.example"
    assert "access-control-allow-credentials" not in response.headers
    assert response.headers["access-control-allow-methods"] == (
        "GET, POST, PATCH, OPTIONS"
    )
    assert "Content-Type" in response.headers["access-control-allow-headers"]


def test_cors_preflight_rejects_unconfigured_origin(settings) -> None:
    settings.cors_origins = "https://frontend.example"
    with TestClient(create_app(settings=settings)) as client:
        response = client.options(
            "/api/v1/health",
            headers={
                "Origin": "https://attacker.example",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_startup_cleanup_failure_logs_only_safe_summary(
    settings, monkeypatch, caplog
) -> None:
    secret_key = "secret-api-key-must-not-be-logged"
    secret_transcript = "full-sensitive-transcript-must-not-be-logged"
    secret_path = "C:/private/audio/marker.wav"
    provider_error = "provider-response-body-must-not-be-logged"
    settings.ai_api_key = secret_key
    engine = build_engine(settings.database_url)
    Base.metadata.create_all(engine)
    factory = build_session_factory(engine)
    now = datetime.now(timezone.utc)
    with factory() as db:
        db.add(
            CaptureSession(
                id="expired-sensitive-session",
                entry_mode="marker",
                activity_name="Sensitive activity",
                marker_transcript=secret_transcript,
                audio_temp_path=secret_path,
                status="marked",
                conversation_json=[],
                error_message=provider_error,
                captured_at=now - timedelta(days=2),
                updated_at=now - timedelta(days=2),
                expires_at=now - timedelta(minutes=1),
            )
        )
        db.commit()
    engine.dispose()
    monkeypatch.setattr(AudioStorage, "delete_session_dir", lambda self, _: False)

    logger = logging.getLogger(LOGGER_NAME)
    logger.addHandler(caplog.handler)
    try:
        with TestClient(create_app(settings=settings)) as client:
            assert client.get("/api/v1/health").status_code == 200
            assert client.app.state.startup_cleanup_result.failed == 1
            with client.app.state.session_factory() as db:
                retained = db.get(CaptureSession, "expired-sensitive-session")
                assert retained is not None
                assert retained.status == "failed"
                assert retained.error_code == "STORAGE_ERROR"
    finally:
        logger.removeHandler(caplog.handler)

    logged = caplog.text
    assert "event=startup_cleanup deleted=0 failed=1 skipped=0" in logged
    assert secret_key not in logged
    assert secret_transcript not in logged
    assert secret_path not in logged
    assert provider_error not in logged
