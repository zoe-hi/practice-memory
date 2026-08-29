from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.orm import Session

from app.ai import ProviderTimeoutError, TranscriptionError
from app.audio import DECISION_SUPPORT_DIR_PREFIX
from app.core.errors import AppError
from app.db.session import get_db
from app.decision_support import create_decision_support
from app.schemas import DecisionSupportResponse
from app.services import transcribe_audio


router = APIRouter(prefix="/decision-support", tags=["decision-support"])
DbSession = Annotated[Session, Depends(get_db)]


def _require_inputs(
    *,
    activity_name: str | None,
    text: str | None,
    audio: UploadFile | None,
) -> tuple[str, str | None]:
    if (text is None) == (audio is None):
        raise AppError(
            400,
            "INPUT_REQUIRED",
            "必须且只能提供 audio 或 text 其中一个。",
        )
    clean_activity = (activity_name or "").strip()
    if not clean_activity:
        raise AppError(400, "INVALID_INPUT", "activity_name 不能为空。")
    clean_text = text.strip() if text is not None else None
    if text is not None and not clean_text:
        raise AppError(400, "INVALID_INPUT", "text 不能为空。")
    return clean_activity, clean_text


@router.post("", response_model=DecisionSupportResponse)
def create_decision_support_endpoint(
    request: Request,
    db: DbSession,
    activity_name: Annotated[str | None, Form()] = None,
    text: Annotated[str | None, Form()] = None,
    audio: Annotated[UploadFile | None, File()] = None,
) -> DecisionSupportResponse:
    clean_activity, clean_text = _require_inputs(
        activity_name=activity_name,
        text=text,
        audio=audio,
    )
    if audio is not None:
        storage = request.app.state.audio_storage
        request_id = f"{DECISION_SUPPORT_DIR_PREFIX}{uuid4()}"
        stored = storage.store(audio, request_id)
        try:
            try:
                concern = transcribe_audio(
                    request.app.state.ai_provider,
                    stored.path,
                )
            except ProviderTimeoutError as exc:
                raise AppError(
                    504,
                    "AI_TIMEOUT",
                    "语音转写超时，请重试或改用文字描述。",
                    retryable=True,
                ) from exc
            except TranscriptionError as exc:
                raise AppError(
                    502,
                    "TRANSCRIPTION_FAILED",
                    "语音转写失败，请重试或改用文字描述。",
                    retryable=True,
                ) from exc
        finally:
            storage.delete_file(stored.path)
    else:
        assert clean_text is not None
        concern = clean_text
    return create_decision_support(
        db,
        request.app.state.ai_provider,
        organization_context=request.app.state.settings.demo_org_context,
        activity_name=clean_activity,
        concern=concern,
    )
