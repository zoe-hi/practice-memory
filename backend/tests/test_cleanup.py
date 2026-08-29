from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.cleanup import cleanup_expired_sessions
from app.db.base import Base
from app.db.session import build_engine, build_session_factory
from app.main import create_app
from app.models import CaptureSession, Experience


def _capture_session(
    *,
    session_id: str,
    expires_at: datetime,
    status: str = "marked",
    confirmed_experience_id: str | None = None,
) -> CaptureSession:
    created_at = expires_at - timedelta(hours=24)
    return CaptureSession(
        id=session_id,
        entry_mode="marker",
        activity_name="清理测试",
        marker_transcript="敏感转写不得进入日志",
        audio_temp_path="internal-path",
        status=status,
        conversation_json=[],
        confirmed_experience_id=confirmed_experience_id,
        captured_at=created_at,
        updated_at=created_at,
        expires_at=expires_at,
    )


def _write_audio(root: Path, session_id: str) -> Path:
    session_dir = root / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    path = session_dir / "marker.wav"
    path.write_bytes(b"audio")
    return path


def test_cleanup_deletes_only_expired_unconfirmed_sessions(
    client: TestClient,
) -> None:
    now = datetime.now(timezone.utc)
    audio_root = Path(client.app.state.settings.audio_storage_dir)
    expired_audio = _write_audio(audio_root, "expired")
    current_audio = _write_audio(audio_root, "current")
    confirmed_audio = _write_audio(audio_root, "confirmed")
    with client.app.state.session_factory() as db:
        experience = Experience(
            id="confirmed-experience",
            activity_name="活动",
            contributor_name="贡献者",
            context="已确认经验",
            recorded_at=now - timedelta(days=2),
        )
        db.add(experience)
        db.flush()
        db.add_all(
            [
                _capture_session(
                    session_id="expired", expires_at=now - timedelta(minutes=1)
                ),
                _capture_session(
                    session_id="current", expires_at=now + timedelta(minutes=1)
                ),
                _capture_session(
                    session_id="confirmed",
                    expires_at=now - timedelta(minutes=1),
                    status="confirmed",
                    confirmed_experience_id=experience.id,
                ),
            ]
        )
        db.commit()

    result = cleanup_expired_sessions(
        client.app.state.session_factory,
        client.app.state.audio_storage,
        now=now,
    )
    assert result.deleted == 1
    assert result.failed == 0
    assert result.skipped == 0
    with client.app.state.session_factory() as db:
        assert db.get(CaptureSession, "expired") is None
        assert db.get(CaptureSession, "current") is not None
        assert db.get(CaptureSession, "confirmed") is not None
        assert db.get(Experience, "confirmed-experience") is not None
    assert not expired_audio.parent.exists()
    assert current_audio.is_file()
    assert confirmed_audio.is_file()


def test_cleanup_failure_is_safe_and_retried(
    client: TestClient, monkeypatch
) -> None:
    now = datetime.now(timezone.utc)
    with client.app.state.session_factory() as db:
        db.add(
            _capture_session(
                session_id="retry-cleanup", expires_at=now - timedelta(minutes=1)
            )
        )
        db.commit()

    storage = client.app.state.audio_storage
    original_delete = storage.delete_session_dir
    monkeypatch.setattr(storage, "delete_session_dir", lambda _: False)
    failed = cleanup_expired_sessions(
        client.app.state.session_factory, storage, now=now
    )
    assert failed.failed == 1
    with client.app.state.session_factory() as db:
        session = db.get(CaptureSession, "retry-cleanup")
        assert session is not None
        assert session.status == "failed"
        assert session.error_code == "STORAGE_ERROR"
        assert session.error_message == "过期会话的临时音频清理失败。"
        assert "internal-path" not in session.error_message

    monkeypatch.setattr(storage, "delete_session_dir", original_delete)
    retried = cleanup_expired_sessions(
        client.app.state.session_factory, storage, now=now
    )
    assert retried.deleted == 1
    assert retried.failed == 0
    with client.app.state.session_factory() as db:
        assert db.get(CaptureSession, "retry-cleanup") is None


def test_application_startup_runs_cleanup(settings) -> None:
    engine = build_engine(settings.database_url)
    Base.metadata.create_all(engine)
    factory = build_session_factory(engine)
    expired_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    with factory() as db:
        db.add(_capture_session(session_id="startup-expired", expires_at=expired_at))
        db.commit()
    engine.dispose()
    audio_path = _write_audio(Path(settings.audio_storage_dir), "startup-expired")

    with TestClient(create_app(settings=settings)) as client:
        assert client.app.state.startup_cleanup_result.deleted == 1
        with client.app.state.session_factory() as db:
            assert db.get(CaptureSession, "startup-expired") is None
        assert not audio_path.parent.exists()


def _command_environment(tmp_path: Path, database_path: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
            "AUDIO_STORAGE_DIR": str(tmp_path / "audio"),
            "AI_PROVIDER": "fake",
            "CORS_ORIGINS": "http://localhost:5173",
            "LOG_LEVEL": "INFO",
        }
    )
    return environment


def test_cleanup_module_command_is_idempotent(tmp_path: Path) -> None:
    database_path = tmp_path / "cleanup-command.db"
    engine = build_engine(f"sqlite:///{database_path.as_posix()}")
    Base.metadata.create_all(engine)
    with build_session_factory(engine)() as db:
        db.add(
            _capture_session(
                session_id="command-expired",
                expires_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
            )
        )
        db.commit()
    engine.dispose()
    audio = _write_audio(tmp_path / "audio", "command-expired")
    backend_dir = Path(__file__).resolve().parents[1]
    environment = _command_environment(tmp_path, database_path)

    first = subprocess.run(
        [sys.executable, "-m", "app.cleanup"],
        cwd=backend_dir,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    second = subprocess.run(
        [sys.executable, "-m", "app.cleanup"],
        cwd=backend_dir,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert first.returncode == 0
    assert "Cleanup deleted=1 failed=0 skipped=0." in first.stdout
    assert second.returncode == 0
    assert "Cleanup deleted=0 failed=0 skipped=0." in second.stdout
    assert not audio.parent.exists()


def test_cleanup_module_command_returns_nonzero_on_safe_path_failure(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "cleanup-failure.db"
    engine = build_engine(f"sqlite:///{database_path.as_posix()}")
    Base.metadata.create_all(engine)
    with build_session_factory(engine)() as db:
        db.add(
            _capture_session(
                session_id="../outside-storage",
                expires_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
            )
        )
        db.commit()
    engine.dispose()
    backend_dir = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "app.cleanup"],
        cwd=backend_dir,
        env=_command_environment(tmp_path, database_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "Cleanup deleted=0 failed=1 skipped=0." in result.stdout
    assert "outside-storage" not in result.stdout
    assert "outside-storage" not in result.stderr
