from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.db.session import get_db
from app.schemas import (
    CaptureSessionCreated,
    CaptureSessionDetail,
    CaptureSessionPatch,
    CaptureSessionSummary,
    CaptureStatus,
    ConfirmRequest,
    DraftPatch,
    EntryMode,
    ExperienceResponse,
    ReflectionResponse,
    TurnPatch,
    TurnResponse,
)
from app.services import (
    confirm_experience,
    create_audio_capture_session,
    create_text_capture_session,
    get_capture_session_detail,
    get_capture_session_list,
    patch_capture_session,
    patch_reflection_answer,
    patch_draft,
    start_reflection,
    submit_audio_turn,
    submit_text_turn,
    transcribe_initial_marker,
)


router = APIRouter(prefix="/capture-sessions", tags=["capture-sessions"])
DbSession = Annotated[Session, Depends(get_db)]


def _require_exactly_one_input(
    text: str | None, audio: UploadFile | None
) -> None:
    if (text is None) == (audio is None):
        raise AppError(
            400,
            "INPUT_REQUIRED",
            "必须且只能提供 audio 或 text 其中一个。",
        )


@router.post("", response_model=CaptureSessionCreated, status_code=status.HTTP_201_CREATED)
def create_capture_session_endpoint(
    request: Request,
    background_tasks: BackgroundTasks,
    db: DbSession,
    text: Annotated[str | None, Form()] = None,
    audio: Annotated[UploadFile | None, File()] = None,
    activity_name: Annotated[str | None, Form()] = None,
    entry_mode: Annotated[EntryMode, Form()] = EntryMode.marker,
) -> CaptureSessionCreated:
    _require_exactly_one_input(text, audio)
    settings: Settings = request.app.state.settings
    if text is not None:
        return create_text_capture_session(
            db,
            settings,
            text=text,
            activity_name=activity_name,
            entry_mode=entry_mode,
        )
    assert audio is not None
    created = create_audio_capture_session(
        db,
        settings,
        request.app.state.audio_storage,
        audio=audio,
        activity_name=activity_name,
        entry_mode=entry_mode,
    )
    background_tasks.add_task(
        transcribe_initial_marker,
        request.app.state.session_factory,
        request.app.state.ai_provider,
        request.app.state.audio_storage,
        created.id,
    )
    return created


@router.get("", response_model=list[CaptureSessionSummary])
def list_capture_sessions_endpoint(
    db: DbSession,
    status_filter: Annotated[CaptureStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[CaptureSessionSummary]:
    return get_capture_session_list(db, status=status_filter, limit=limit)


@router.get("/{session_id}", response_model=CaptureSessionDetail)
def get_capture_session_endpoint(
    session_id: str, db: DbSession
) -> CaptureSessionDetail:
    return get_capture_session_detail(db, session_id)


@router.patch("/{session_id}", response_model=CaptureSessionDetail)
def patch_capture_session_endpoint(
    session_id: str, patch: CaptureSessionPatch, db: DbSession
) -> CaptureSessionDetail:
    return patch_capture_session(db, session_id, patch)


@router.post("/{session_id}/start-reflection", response_model=ReflectionResponse)
def start_reflection_endpoint(
    session_id: str, request: Request, db: DbSession
) -> ReflectionResponse:
    return start_reflection(
        db,
        request.app.state.ai_provider,
        request.app.state.audio_storage,
        session_id,
    )


@router.post("/{session_id}/turns", response_model=TurnResponse)
def submit_turn_endpoint(
    session_id: str,
    request: Request,
    db: DbSession,
    text: Annotated[str | None, Form()] = None,
    audio: Annotated[UploadFile | None, File()] = None,
) -> TurnResponse:
    _require_exactly_one_input(text, audio)
    if text is not None:
        return submit_text_turn(
            db, request.app.state.ai_provider, session_id, text
        )
    assert audio is not None
    return submit_audio_turn(
        db,
        request.app.state.ai_provider,
        request.app.state.audio_storage,
        session_id,
        audio,
    )


@router.patch("/{session_id}/turns/{turn_id}", response_model=ReflectionResponse)
def patch_reflection_answer_endpoint(
    session_id: str,
    turn_id: str,
    patch: TurnPatch,
    request: Request,
    db: DbSession,
) -> ReflectionResponse:
    return patch_reflection_answer(
        db, request.app.state.ai_provider, session_id, turn_id, patch
    )


@router.patch("/{session_id}/draft", response_model=CaptureSessionDetail)
def patch_draft_endpoint(
    session_id: str, patch: DraftPatch, db: DbSession
) -> CaptureSessionDetail:
    return patch_draft(db, session_id, patch)


@router.post("/{session_id}/confirm", response_model=ExperienceResponse)
def confirm_endpoint(
    session_id: str,
    body: ConfirmRequest,
    request: Request,
    response: Response,
    db: DbSession,
) -> ExperienceResponse:
    experience, created = confirm_experience(
        db, request.app.state.audio_storage, session_id, body
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return experience
