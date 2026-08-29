from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.audio import AudioStorage
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.base import Base
from app.db.session import build_engine, build_session_factory
from app.models import CaptureSession
from app.schemas import CaptureStatus


@dataclass(frozen=True, slots=True)
class CleanupResult:
    deleted: int = 0
    failed: int = 0
    skipped: int = 0


def cleanup_expired_sessions(
    session_factory: sessionmaker[Session],
    storage: AudioStorage,
    *,
    now: datetime | None = None,
) -> CleanupResult:
    cutoff = now or datetime.now(timezone.utc)
    with session_factory() as db:
        expired_ids = list(
            db.scalars(
                select(CaptureSession.id).where(
                    CaptureSession.expires_at < cutoff,
                    CaptureSession.status != CaptureStatus.confirmed.value,
                    CaptureSession.confirmed_experience_id.is_(None),
                )
            )
        )

    deleted = 0
    failed = 0
    skipped = 0
    for session_id in expired_ids:
        with session_factory() as db:
            session = db.get(CaptureSession, session_id)
            if session is None:
                skipped += 1
                continue
            if (
                session.status == CaptureStatus.confirmed.value
                or session.confirmed_experience_id is not None
            ):
                skipped += 1
                continue
            if not storage.delete_session_dir(session.id):
                session.status = CaptureStatus.failed.value
                session.error_code = "STORAGE_ERROR"
                session.error_message = "过期会话的临时音频清理失败。"
                session.updated_at = datetime.now(timezone.utc)
                db.commit()
                failed += 1
                continue
            db.delete(session)
            db.commit()
            deleted += 1
    return CleanupResult(deleted=deleted, failed=failed, skipped=skipped)


def run_cleanup_command() -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    url = make_url(settings.database_url)
    if url.get_backend_name() == "sqlite" and url.database not in (None, "", ":memory:"):
        Path(url.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    storage = AudioStorage(settings.audio_storage_dir, settings.max_audio_bytes)
    storage.ensure_root()
    engine = build_engine(settings.database_url)
    try:
        Base.metadata.create_all(engine)
        result = cleanup_expired_sessions(build_session_factory(engine), storage)
    finally:
        engine.dispose()
    print(
        f"Cleanup deleted={result.deleted} failed={result.failed} skipped={result.skipped}."
    )
    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(run_cleanup_command())
