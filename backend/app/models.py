from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid4())


class Experience(Base):
    __tablename__ = "experiences"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    activity_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contributor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contributor_role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_and_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    went_well: Mapped[str | None] = mapped_column(Text, nullable=True)
    shortcomings: Mapped[str | None] = mapped_column(Text, nullable=True)
    things_to_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    open_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class CaptureSession(Base):
    __tablename__ = "capture_sessions"
    __table_args__ = (
        CheckConstraint(
            "entry_mode IN ('marker', 'direct_reflection')",
            name="ck_capture_sessions_entry_mode",
        ),
        CheckConstraint(
            "status IN ('marked', 'reflecting', 'needs_confirmation', 'confirmed', 'failed')",
            name="ck_capture_sessions_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    entry_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="marker")
    activity_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    marker_transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_temp_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="marked", index=True)
    conversation_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    draft_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    confirmed_experience_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("experiences.id"),
        nullable=True,
        unique=True,
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
