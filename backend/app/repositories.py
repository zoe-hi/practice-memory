from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.matching import normalize_search_text
from app.models import CaptureSession, Experience


def get_capture_session(db: Session, session_id: str) -> CaptureSession | None:
    return db.get(CaptureSession, session_id)


def list_capture_sessions(
    db: Session, *, status: str | None, limit: int
) -> list[CaptureSession]:
    statement: Select[tuple[CaptureSession]] = select(CaptureSession)
    if status is not None:
        statement = statement.where(CaptureSession.status == status)
    statement = statement.order_by(CaptureSession.captured_at.desc()).limit(limit)
    return list(db.scalars(statement))


def get_experience(db: Session, experience_id: str) -> Experience | None:
    return db.get(Experience, experience_id)


def list_experiences(
    db: Session, *, activity_name: str | None, limit: int
) -> list[Experience]:
    statement: Select[tuple[Experience]] = select(Experience).order_by(
        Experience.recorded_at.desc(), Experience.id.asc()
    )
    if activity_name is None:
        return list(db.scalars(statement.limit(limit)))
    normalized_name = normalize_search_text(activity_name)
    return [
        experience
        for experience in db.scalars(statement)
        if normalize_search_text(experience.activity_name) == normalized_name
    ][:limit]


def find_experience_candidates(
    db: Session, *, activity_name: str, limit: int = 20
) -> list[Experience]:
    statement: Select[tuple[Experience]] = select(Experience).order_by(
        Experience.recorded_at.desc(), Experience.id.asc()
    )
    experiences = list(db.scalars(statement))
    normalized_name = normalize_search_text(activity_name)
    exact = [
        experience
        for experience in experiences
        if normalize_search_text(experience.activity_name) == normalized_name
    ]
    if exact:
        return exact[:limit]
    return [
        experience
        for experience in experiences
        if normalized_name in normalize_search_text(experience.activity_name)
        or normalize_search_text(experience.activity_name) in normalized_name
    ][:limit]
