from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from app.ai import (
    AIProvider,
    ProviderInvalidOutputError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    TranscriptionError,
)
from app.audio import AudioStorage
from app.core.config import Settings
from app.core.errors import AppError
from app.models import CaptureSession, Experience, new_uuid
from app.repositories import get_capture_session, get_experience, list_capture_sessions
from app.schemas import (
    CaptureSessionCreated,
    CaptureSessionDetail,
    CaptureSessionPatch,
    CaptureSessionSummary,
    CaptureStatus,
    ConfirmRequest,
    ConversationMessage,
    DRAFT_TEXT_FIELDS,
    DraftPatch,
    EntryMode,
    ExperienceContent,
    ExperienceDraft,
    ExperienceResponse,
    MessageKind,
    MessageRole,
    MessageSource,
    NextQuestion,
    ReflectionAdvanceResult,
    ReflectionResponse,
    TurnPatch,
    TurnResponse,
)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _message(
    *, role: MessageRole, kind: MessageKind, text: str, source: MessageSource
) -> ConversationMessage:
    return ConversationMessage(
        turn_id=str(uuid4()),
        role=role,
        kind=kind,
        text=text,
        source=source,
        created_at=now_utc(),
    )


def _messages(session: CaptureSession) -> list[ConversationMessage]:
    return [ConversationMessage.model_validate(item) for item in session.conversation_json]


def _store_messages(
    session: CaptureSession, messages: list[ConversationMessage]
) -> None:
    session.conversation_json = [
        message.model_dump(mode="json") for message in messages
    ]
    session.updated_at = now_utc()


def _public_draft(session: CaptureSession) -> ExperienceContent | None:
    if session.draft_json is None:
        return None
    draft = ExperienceDraft.model_validate(session.draft_json)
    return ExperienceContent.model_validate(
        {field: getattr(draft, field) for field in DRAFT_TEXT_FIELDS}
    )


def _capture_or_404(db: Session, session_id: str) -> CaptureSession:
    session = get_capture_session(db, session_id)
    if session is None:
        raise AppError(404, "SESSION_NOT_FOUND", "会话不存在。")
    return session


def _detail(session: CaptureSession) -> CaptureSessionDetail:
    return CaptureSessionDetail(
        id=session.id,
        entry_mode=session.entry_mode,
        activity_name=session.activity_name,
        marker_transcript=session.marker_transcript,
        status=session.status,
        conversation=_messages(session),
        draft=_public_draft(session),
        can_confirm=session.status == CaptureStatus.needs_confirmation,
        captured_at=as_utc(session.captured_at),
        updated_at=as_utc(session.updated_at),
        expires_at=as_utc(session.expires_at),
    )


def create_text_capture_session(
    db: Session,
    settings: Settings,
    *,
    text: str,
    activity_name: str | None,
    entry_mode: EntryMode,
) -> CaptureSessionCreated:
    clean_text = text.strip()
    if not clean_text:
        raise AppError(400, "INPUT_REQUIRED", "必须提供非空文字。")
    if activity_name is not None:
        activity_name = activity_name.strip() or None

    created_at = now_utc()
    marker = _message(
        role=MessageRole.user,
        kind=MessageKind.marker,
        text=clean_text,
        source=MessageSource.text,
    )
    session = CaptureSession(
        entry_mode=entry_mode.value,
        activity_name=activity_name,
        marker_transcript=clean_text,
        status=(
            CaptureStatus.reflecting.value
            if entry_mode == EntryMode.direct_reflection
            else CaptureStatus.marked.value
        ),
        conversation_json=[marker.model_dump(mode="json")],
        captured_at=created_at,
        updated_at=created_at,
        expires_at=created_at + timedelta(hours=settings.session_ttl_hours),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return CaptureSessionCreated(
        id=session.id,
        entry_mode=session.entry_mode,
        activity_name=session.activity_name,
        status=session.status,
        marker_transcript=session.marker_transcript,
        captured_at=as_utc(session.captured_at),
        expires_at=as_utc(session.expires_at),
    )


def create_audio_capture_session(
    db: Session,
    settings: Settings,
    storage: AudioStorage,
    *,
    audio: UploadFile,
    activity_name: str | None,
    entry_mode: EntryMode,
) -> CaptureSessionCreated:
    session_id = new_uuid()
    stored = storage.store(audio, session_id)
    if activity_name is not None:
        activity_name = activity_name.strip() or None
    created_at = now_utc()
    session = CaptureSession(
        id=session_id,
        entry_mode=entry_mode.value,
        activity_name=activity_name,
        marker_transcript=None,
        audio_temp_path=stored.path,
        status=(
            CaptureStatus.reflecting.value
            if entry_mode == EntryMode.direct_reflection
            else CaptureStatus.marked.value
        ),
        conversation_json=[],
        captured_at=created_at,
        updated_at=created_at,
        expires_at=created_at + timedelta(hours=settings.session_ttl_hours),
    )
    try:
        db.add(session)
        db.commit()
        db.refresh(session)
    except Exception as exc:
        db.rollback()
        storage.delete_session_dir(session_id)
        raise AppError(500, "STORAGE_ERROR", "会话无法保存。") from exc
    return CaptureSessionCreated(
        id=session.id,
        entry_mode=session.entry_mode,
        activity_name=session.activity_name,
        status=session.status,
        marker_transcript=None,
        captured_at=as_utc(session.captured_at),
        expires_at=as_utc(session.expires_at),
    )


def transcribe_audio(provider: AIProvider, audio_path: str) -> str:
    try:
        transcript = provider.transcribe(audio_path).strip()
    except ProviderTimeoutError:
        raise
    except TranscriptionError:
        raise
    except (ProviderInvalidOutputError, ProviderUnavailableError) as exc:
        raise TranscriptionError("provider transcription failed") from exc
    except Exception as exc:
        raise TranscriptionError("provider transcription failed") from exc
    if not transcript:
        raise TranscriptionError("provider returned an empty transcript")
    return transcript


def _apply_initial_transcript(
    session: CaptureSession, transcript: str, *, source: MessageSource
) -> None:
    session.marker_transcript = transcript
    messages = _messages(session)
    marker = next(
        (message for message in messages if message.kind == MessageKind.marker), None
    )
    if marker is None:
        messages.insert(
            0,
            _message(
                role=MessageRole.user,
                kind=MessageKind.marker,
                text=transcript,
                source=source,
            ),
        )
    else:
        marker.text = transcript
        marker.source = source
    _store_messages(session, messages)
    session.error_code = None
    session.error_message = None


def _run_initial_marker_transcription(
    session_factory: sessionmaker[Session],
    provider: AIProvider,
    storage: AudioStorage,
    session_id: str,
) -> None:
    """Best-effort background transcription; never leaks provider failures."""
    with session_factory() as db:
        session = get_capture_session(db, session_id)
        if session is None or session.marker_transcript is not None:
            return
        audio_path = storage.existing_path(session.audio_temp_path)
        if audio_path is None:
            session.status = CaptureStatus.failed.value
            session.error_code = "STORAGE_ERROR"
            session.error_message = "初始音频文件不可用。"
            db.commit()
            return

    try:
        transcript = transcribe_audio(provider, str(audio_path))
    except (ProviderTimeoutError, TranscriptionError) as exc:
        with session_factory() as db:
            session = get_capture_session(db, session_id)
            if session is not None and session.marker_transcript is None:
                timed_out = isinstance(exc, ProviderTimeoutError)
                session.error_code = "AI_TIMEOUT" if timed_out else "TRANSCRIPTION_FAILED"
                session.error_message = (
                    "初始音频转写超时，可稍后重试。"
                    if timed_out
                    else "初始音频转写失败，可稍后重试。"
                )
                session.updated_at = now_utc()
                db.commit()
        return

    # Re-read after the provider call so a contributor's manual correction wins.
    with session_factory() as db:
        session = get_capture_session(db, session_id)
        if session is None or session.marker_transcript is not None:
            return
        _apply_initial_transcript(session, transcript, source=MessageSource.audio)
        db.commit()


def transcribe_initial_marker(
    session_factory: sessionmaker[Session],
    provider: AIProvider,
    storage: AudioStorage,
    session_id: str,
) -> None:
    try:
        _run_initial_marker_transcription(
            session_factory, provider, storage, session_id
        )
    except Exception:
        # The session and audio are already durable. Background infrastructure
        # failures must not turn a successful create response into an exception.
        return


def get_capture_session_detail(db: Session, session_id: str) -> CaptureSessionDetail:
    return _detail(_capture_or_404(db, session_id))


def get_capture_session_list(
    db: Session, *, status: CaptureStatus | None, limit: int
) -> list[CaptureSessionSummary]:
    sessions = list_capture_sessions(
        db, status=status.value if status is not None else None, limit=limit
    )
    return [
        CaptureSessionSummary(
            id=session.id,
            activity_name=session.activity_name,
            marker_transcript_preview=(
                session.marker_transcript[:120]
                if session.marker_transcript is not None
                else None
            ),
            status=session.status,
            captured_at=as_utc(session.captured_at),
        )
        for session in sessions
    ]


def patch_capture_session(
    db: Session, session_id: str, patch: CaptureSessionPatch
) -> CaptureSessionDetail:
    session = _capture_or_404(db, session_id)
    if session.status in {CaptureStatus.confirmed, CaptureStatus.failed}:
        raise AppError(409, "INVALID_STATE", "当前会话不能执行此操作。")

    values = patch.model_dump(exclude_unset=True)
    if "activity_name" in values:
        activity_name = values["activity_name"]
        session.activity_name = activity_name.strip() or None if activity_name else None

    if "marker_transcript" in values:
        transcript = values["marker_transcript"]
        if transcript is None or not transcript.strip():
            raise AppError(422, "INVALID_INPUT", "初始转写不能为空。")
        transcript = transcript.strip()
        session.marker_transcript = transcript
        messages = _messages(session)
        marker = next(
            (message for message in messages if message.kind == MessageKind.marker),
            None,
        )
        if marker is None:
            messages.insert(
                0,
                _message(
                    role=MessageRole.user,
                    kind=MessageKind.marker,
                    text=transcript,
                    source=MessageSource.text,
                ),
            )
        else:
            marker.text = transcript
            marker.source = MessageSource.text
        _store_messages(session, messages)

    session.updated_at = now_utc()
    db.commit()
    db.refresh(session)
    return _detail(session)


def _question_count(messages: list[ConversationMessage]) -> int:
    return sum(
        message.role == MessageRole.assistant
        and message.kind == MessageKind.question
        for message in messages
    )


def _safe_draft(
    draft: ExperienceDraft, messages: list[ConversationMessage]
) -> ExperienceDraft:
    valid_turns = {message.turn_id for message in messages}
    source_turn_ids: dict[str, list[str]] = {}
    warnings = list(draft.warnings)
    for field in DRAFT_TEXT_FIELDS:
        sources = draft.source_turn_ids.get(field, [])
        valid_sources = [
            source for source in sources if source in valid_turns or source == "manual_edit"
        ]
        if len(valid_sources) != len(sources):
            warnings.append(f"invalid_source_removed:{field}")
        source_turn_ids[field] = valid_sources
    return draft.model_copy(
        update={"source_turn_ids": source_turn_ids, "warnings": warnings}
    )


MAX_REFLECTION_QUESTIONS = 5

def _advance(
    session: CaptureSession,
    provider: AIProvider,
    messages: list[ConversationMessage],
) -> tuple[NextQuestion | None, ExperienceContent | None]:
    count = _question_count(messages)
    try:
        result = provider.advance_reflection(
            messages,
            ExperienceDraft.model_validate(session.draft_json)
            if session.draft_json
            else None,
            count,
        )
        result = ReflectionAdvanceResult.model_validate(result)
    except ProviderTimeoutError as exc:
        raise AppError(
            504, "AI_TIMEOUT", "AI 服务响应超时，请重试。", retryable=True
        ) from exc
    except ProviderInvalidOutputError as exc:
        raise AppError(
            502, "AI_INVALID_OUTPUT", "AI 返回内容无法校验。", retryable=True
        ) from exc
    except ProviderUnavailableError as exc:
        raise AppError(
            502,
            "AI_INVALID_OUTPUT",
            "AI 服务暂时不可用，请重试。",
            retryable=exc.retryable,
        ) from exc
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            502, "AI_INVALID_OUTPUT", "AI 返回内容无法校验。", retryable=True
        ) from exc

    if result.ready_for_confirmation:
        assert result.draft is not None
        draft = _safe_draft(result.draft, messages)
        session.draft_json = draft.model_dump(mode="json")
        session.status = CaptureStatus.needs_confirmation.value
        session.updated_at = now_utc()
        return None, ExperienceContent.model_validate(
            {field: getattr(draft, field) for field in DRAFT_TEXT_FIELDS}
        )

    if count >= MAX_REFLECTION_QUESTIONS or not result.next_question:
        raise AppError(502, "AI_INVALID_OUTPUT", "AI 未在问题上限内生成草稿。", True)
    question = _message(
        role=MessageRole.assistant,
        kind=MessageKind.question,
        text=result.next_question,
        source=MessageSource.generated,
    )
    messages.append(question)
    _store_messages(session, messages)
    return NextQuestion(turn_id=question.turn_id, text=question.text), None


def start_reflection(
    db: Session,
    provider: AIProvider,
    storage: AudioStorage,
    session_id: str,
) -> ReflectionResponse:
    session = _capture_or_404(db, session_id)
    messages = _messages(session)
    is_direct_start = (
        session.entry_mode == EntryMode.direct_reflection
        and session.status == CaptureStatus.reflecting
        and _question_count(messages) == 0
    )
    if session.status != CaptureStatus.marked and not is_direct_start:
        raise AppError(409, "INVALID_STATE", "当前会话不能开始复盘。")
    if not session.marker_transcript:
        audio_path = storage.existing_path(session.audio_temp_path)
        if audio_path is None:
            session.status = CaptureStatus.failed.value
            session.error_code = "STORAGE_ERROR"
            session.error_message = "初始音频文件不可用。"
            session.updated_at = now_utc()
            db.commit()
            raise AppError(
                500, "STORAGE_ERROR", "初始音频文件不可用。", retryable=False
            )
        try:
            transcript = transcribe_audio(provider, str(audio_path))
        except ProviderTimeoutError as exc:
            raise AppError(
                504, "AI_TIMEOUT", "音频转写超时，请重试。", retryable=True
            ) from exc
        except TranscriptionError as exc:
            raise AppError(
                502, "TRANSCRIPTION_FAILED", "音频转写失败，请重试。", retryable=True
            ) from exc
        _apply_initial_transcript(session, transcript, source=MessageSource.audio)
        messages = _messages(session)

    session.status = CaptureStatus.reflecting.value
    next_question, draft = _advance(session, provider, messages)
    db.commit()
    return ReflectionResponse(
        session_id=session.id,
        status=session.status,
        next_question=next_question,
        draft=draft,
    )


def _submit_turn(
    db: Session,
    provider: AIProvider,
    session: CaptureSession,
    text: str,
    source: MessageSource,
) -> TurnResponse:
    answer_text = text.strip()
    if not answer_text:
        raise AppError(400, "INPUT_REQUIRED", "必须提供非空文字。")

    messages = _messages(session)
    answer = _message(
        role=MessageRole.user,
        kind=MessageKind.answer,
        text=answer_text,
        source=source,
    )
    messages.append(answer)
    _store_messages(session, messages)
    next_question, draft = _advance(session, provider, messages)
    db.commit()
    return TurnResponse(
        session_id=session.id,
        status=session.status,
        answer_transcript=answer_text,
        next_question=next_question,
        draft=draft,
    )


def submit_text_turn(
    db: Session, provider: AIProvider, session_id: str, text: str
) -> TurnResponse:
    session = _capture_or_404(db, session_id)
    if session.status != CaptureStatus.reflecting:
        raise AppError(409, "INVALID_STATE", "当前会话不能提交回答。")
    return _submit_turn(
        db, provider, session, text, source=MessageSource.text
    )


def patch_reflection_answer(
    db: Session,
    provider: AIProvider,
    session_id: str,
    answer_turn_id: str,
    patch: TurnPatch,
) -> ReflectionResponse:
    """Correct one answer and invalidate every AI message derived from its old text."""
    session = _capture_or_404(db, session_id)
    if session.status != CaptureStatus.reflecting:
        raise AppError(409, "INVALID_STATE", "当前会话不能修改复盘回答。")

    messages = _messages(session)
    answer_index = next(
        (index for index, message in enumerate(messages) if message.turn_id == answer_turn_id),
        None,
    )
    if answer_index is None:
        raise AppError(404, "TURN_NOT_FOUND", "要修改的回答不存在。")
    answer = messages[answer_index]
    if (
        answer.role != MessageRole.user
        or answer.kind != MessageKind.answer
        or answer_index == 0
        or messages[answer_index - 1].kind != MessageKind.question
    ):
        raise AppError(400, "INVALID_TURN", "只能修改 AI 复盘中的文字回答。")

    messages[answer_index] = answer.model_copy(
        update={"text": patch.text, "source": MessageSource.text}
    )
    # Subsequent questions and answers relied on the old answer and are stale.
    messages = messages[: answer_index + 1]
    session.draft_json = None
    _store_messages(session, messages)
    next_question, draft = _advance(session, provider, messages)
    db.commit()
    return ReflectionResponse(
        session_id=session.id,
        status=session.status,
        next_question=next_question,
        draft=draft,
    )


def submit_audio_turn(
    db: Session,
    provider: AIProvider,
    storage: AudioStorage,
    session_id: str,
    audio: UploadFile,
) -> TurnResponse:
    session = _capture_or_404(db, session_id)
    if session.status != CaptureStatus.reflecting:
        raise AppError(409, "INVALID_STATE", "当前会话不能提交回答。")
    stored = storage.store(audio, session.id)
    try:
        transcript = transcribe_audio(provider, stored.path)
    except ProviderTimeoutError as exc:
        storage.best_effort_delete_file(stored.path)
        raise AppError(
            504, "AI_TIMEOUT", "音频转写超时，请重新上传。", retryable=True
        ) from exc
    except TranscriptionError as exc:
        storage.best_effort_delete_file(stored.path)
        raise AppError(
            502, "TRANSCRIPTION_FAILED", "音频转写失败，请重新上传。", retryable=True
        ) from exc
    storage.delete_file(stored.path)
    return _submit_turn(
        db, provider, session, transcript, source=MessageSource.audio
    )


def patch_draft(
    db: Session, session_id: str, patch: DraftPatch
) -> CaptureSessionDetail:
    session = _capture_or_404(db, session_id)
    if session.status != CaptureStatus.needs_confirmation or session.draft_json is None:
        raise AppError(409, "INVALID_STATE", "当前会话没有可修改的草稿。")
    draft = ExperienceDraft.model_validate(session.draft_json)
    changes = patch.model_dump(exclude_unset=True)
    sources = dict(draft.source_turn_ids)
    for field, value in changes.items():
        if isinstance(value, str):
            value = value.strip() or None
        setattr(draft, field, value)
        sources[field] = ["manual_edit"]
    draft.source_turn_ids = sources
    session.draft_json = draft.model_dump(mode="json")
    session.updated_at = now_utc()
    db.commit()
    db.refresh(session)
    return _detail(session)


def experience_to_response(experience: Experience) -> ExperienceResponse:
    return ExperienceResponse(
        id=experience.id,
        activity_name=experience.activity_name,
        contributor_name=experience.contributor_name,
        contributor_role=experience.contributor_role,
        context=experience.context,
        action_and_reason=experience.action_and_reason,
        observed_result=experience.observed_result,
        went_well=experience.went_well,
        shortcomings=experience.shortcomings,
        things_to_note=experience.things_to_note,
        open_question=experience.open_question,
        recorded_at=as_utc(experience.recorded_at),
        updated_at=as_utc(experience.updated_at),
    )


def confirm_experience(
    db: Session,
    storage: AudioStorage,
    session_id: str,
    request: ConfirmRequest,
) -> tuple[ExperienceResponse, bool]:
    # SQLite ignores SELECT FOR UPDATE. BEGIN IMMEDIATE serializes confirmations so
    # concurrent repeat clicks re-read confirmed_experience_id after the first commit.
    if db.bind is not None and db.bind.dialect.name == "sqlite":
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    session = _capture_or_404(db, session_id)
    if session.confirmed_experience_id:
        existing = get_experience(db, session.confirmed_experience_id)
        if existing is None:
            raise AppError(500, "STORAGE_ERROR", "已确认经验无法读取。")
        return experience_to_response(existing), False

    if session.status != CaptureStatus.needs_confirmation or session.draft_json is None:
        raise AppError(409, "INVALID_STATE", "当前会话不能确认。")
    activity_name = (session.activity_name or "").strip()
    if not activity_name:
        raise AppError(422, "INVALID_DRAFT", "确认前必须填写活动名称。")
    draft = ExperienceDraft.model_validate(session.draft_json)
    if not any(
        isinstance(getattr(draft, field), str) and getattr(draft, field).strip()
        for field in DRAFT_TEXT_FIELDS
    ):
        raise AppError(422, "INVALID_DRAFT", "经验正文至少需要一个非空字段。")

    experience = Experience(
        activity_name=activity_name,
        contributor_name=request.contributor_name.strip(),
        contributor_role=(request.contributor_role or "").strip() or None,
        recorded_at=session.captured_at,
        **{field: getattr(draft, field) for field in DRAFT_TEXT_FIELDS},
    )
    db.add(experience)
    db.flush()
    session.confirmed_experience_id = experience.id
    session.status = CaptureStatus.confirmed.value
    session.updated_at = now_utc()
    db.commit()
    db.refresh(experience)
    if session.audio_temp_path and storage.delete_session_dir(session.id):
        try:
            session.audio_temp_path = None
            db.commit()
        except Exception:
            db.rollback()
    return experience_to_response(experience), True
