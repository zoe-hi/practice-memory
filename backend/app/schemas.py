from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EntryMode(StrEnum):
    marker = "marker"
    direct_reflection = "direct_reflection"


class CaptureStatus(StrEnum):
    marked = "marked"
    reflecting = "reflecting"
    needs_confirmation = "needs_confirmation"
    confirmed = "confirmed"
    failed = "failed"


class MessageRole(StrEnum):
    user = "user"
    assistant = "assistant"


class MessageKind(StrEnum):
    marker = "marker"
    question = "question"
    answer = "answer"


class MessageSource(StrEnum):
    audio = "audio"
    text = "text"
    generated = "generated"


class ConversationMessage(StrictModel):
    turn_id: str
    role: MessageRole
    kind: MessageKind
    text: str
    source: MessageSource
    created_at: datetime


DRAFT_TEXT_FIELDS = (
    "context",
    "action_and_reason",
    "observed_result",
    "went_well",
    "shortcomings",
    "things_to_note",
    "open_question",
)


class ExperienceContent(StrictModel):
    context: str | None = None
    action_and_reason: str | None = None
    observed_result: str | None = None
    went_well: str | None = None
    shortcomings: str | None = None
    things_to_note: str | None = None
    open_question: str | None = None


class ExperienceDraft(ExperienceContent):
    source_turn_ids: dict[str, list[str]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class ReflectionAdvanceResult(StrictModel):
    ready_for_confirmation: bool
    next_question: str | None = None
    draft: ExperienceDraft | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "ReflectionAdvanceResult":
        if self.ready_for_confirmation:
            if self.draft is None or self.next_question is not None:
                raise ValueError("ready result must have a draft and no question")
        elif not self.next_question or self.draft is not None:
            raise ValueError("continuing result must have a question and no draft")
        return self


class CaptureSessionPatch(StrictModel):
    activity_name: str | None = None
    marker_transcript: str | None = None

    @model_validator(mode="after")
    def require_change(self) -> "CaptureSessionPatch":
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        return self


class DraftPatch(StrictModel):
    context: str | None = None
    action_and_reason: str | None = None
    observed_result: str | None = None
    went_well: str | None = None
    shortcomings: str | None = None
    things_to_note: str | None = None
    open_question: str | None = None

    @model_validator(mode="after")
    def require_change(self) -> "DraftPatch":
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        return self


class TurnPatch(StrictModel):
    text: str = Field(min_length=1)

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text cannot be blank")
        return value


class ConfirmRequest(StrictModel):
    contributor_name: str = Field(min_length=1, max_length=255)
    contributor_role: str | None = Field(default=None, max_length=255)

    @field_validator("contributor_name")
    @classmethod
    def contributor_name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("contributor_name cannot be blank")
        return value


class CaptureSessionCreated(StrictModel):
    id: str
    entry_mode: EntryMode
    activity_name: str | None
    status: CaptureStatus
    marker_transcript: str | None
    captured_at: datetime
    expires_at: datetime


class CaptureSessionSummary(StrictModel):
    id: str
    activity_name: str | None
    marker_transcript_preview: str | None
    status: CaptureStatus
    captured_at: datetime


class CaptureSessionDetail(StrictModel):
    id: str
    entry_mode: EntryMode
    activity_name: str | None
    marker_transcript: str | None
    status: CaptureStatus
    conversation: list[ConversationMessage]
    draft: ExperienceContent | None
    can_confirm: bool
    captured_at: datetime
    updated_at: datetime
    expires_at: datetime


class NextQuestion(StrictModel):
    turn_id: str
    text: str


class ReflectionResponse(StrictModel):
    session_id: str
    status: CaptureStatus
    next_question: NextQuestion | None
    draft: ExperienceContent | None


class TurnResponse(ReflectionResponse):
    answer_transcript: str


class ExperienceResponse(ExperienceContent):
    id: str
    activity_name: str
    contributor_name: str
    contributor_role: str | None
    recorded_at: datetime
    updated_at: datetime


class ExperienceCandidate(ExperienceContent):
    id: str
    activity_name: str


class ExperienceMatch(StrictModel):
    experience_id: str
    why_similar: str = Field(min_length=1)

    @field_validator("experience_id", "why_similar")
    @classmethod
    def match_text_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("match values cannot be blank")
        return value


class ExperienceRankingResult(StrictModel):
    match: ExperienceMatch | None


class ExperienceSearchRequest(StrictModel):
    activity_name: str = Field(min_length=1, max_length=255)
    concern: str = Field(min_length=1, max_length=4000)

    @field_validator("activity_name", "concern")
    @classmethod
    def search_text_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("search values cannot be blank")
        return value


class ExperienceSearchMatch(StrictModel):
    experience: ExperienceResponse
    why_similar: str


class ExperienceSearchResponse(StrictModel):
    match: ExperienceSearchMatch | None


DecisionBasisField = Literal[
    "context",
    "action_and_reason",
    "observed_result",
    "went_well",
    "shortcomings",
    "things_to_note",
    "open_question",
]


def _strip_required_text(value: object) -> object:
    if isinstance(value, str):
        value = value.strip()
        if not value:
            raise ValueError("text cannot be blank")
    return value


def _strip_optional_text(value: object) -> object:
    if isinstance(value, str):
        return value.strip() or None
    return value


class DecisionConsiderationDraft(StrictModel):
    direction: str
    tradeoff: str | None = None
    basis_fields: list[DecisionBasisField] = Field(min_length=1, max_length=7)

    _normalize_direction = field_validator("direction", mode="before")(
        _strip_required_text
    )
    _normalize_tradeoff = field_validator("tradeoff", mode="before")(
        _strip_optional_text
    )


class DecisionSupportAIResult(StrictModel):
    understanding: str
    considerations: list[DecisionConsiderationDraft] = Field(max_length=2)
    question_to_consider: str | None = None

    _normalize_understanding = field_validator("understanding", mode="before")(
        _strip_required_text
    )
    _normalize_question = field_validator("question_to_consider", mode="before")(
        _strip_optional_text
    )


class DecisionConsideration(StrictModel):
    direction: str
    tradeoff: str | None = None
    basis_experience_id: UUID

    _normalize_direction = field_validator("direction", mode="before")(
        _strip_required_text
    )
    _normalize_tradeoff = field_validator("tradeoff", mode="before")(
        _strip_optional_text
    )


class DecisionSupportResponse(StrictModel):
    activity_name: str
    concern_transcript: str
    understanding: str
    match: ExperienceSearchMatch | None
    considerations: list[DecisionConsideration] = Field(max_length=2)
    question_to_consider: str | None = None

    _normalize_activity_name = field_validator("activity_name", mode="before")(
        _strip_required_text
    )
    _normalize_concern = field_validator("concern_transcript", mode="before")(
        _strip_required_text
    )
    _normalize_understanding = field_validator("understanding", mode="before")(
        _strip_required_text
    )
    _normalize_question = field_validator("question_to_consider", mode="before")(
        _strip_optional_text
    )
