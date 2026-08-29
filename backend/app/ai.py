from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from app.matching import rank_experiences_locally
from app.schemas import (
    ConversationMessage,
    ExperienceCandidate,
    ExperienceDraft,
    ExperienceMatch,
    MessageKind,
    ReflectionAdvanceResult,
)


class AIProvider(Protocol):
    def transcribe(self, audio_path: str) -> str: ...

    def advance_reflection(
        self,
        messages: list[ConversationMessage],
        current_draft: ExperienceDraft | None,
        question_count: int,
    ) -> ReflectionAdvanceResult: ...

    def rank_experiences(
        self,
        concern: str,
        candidates: list[ExperienceCandidate],
    ) -> ExperienceMatch | None: ...


class AIProviderError(RuntimeError):
    """Safe, provider-neutral failure exposed to the business layer."""


class ProviderTimeoutError(AIProviderError):
    """A provider request exceeded the configured client timeout."""


class ProviderUnavailableError(AIProviderError):
    """A provider request failed before a valid model result was available."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class ProviderInvalidOutputError(AIProviderError):
    """A model response could not be parsed into the documented contract."""


class TranscriptionError(AIProviderError):
    """Provider-neutral, safe-to-map transcription failure."""


class FakeAIProvider:
    """Deterministic, offline provider for the Golden Path and tests."""

    def __init__(self, transcription_text: str | None = None) -> None:
        self.transcription_text = transcription_text

    def transcribe(self, audio_path: str) -> str:
        del audio_path
        if self.transcription_text is None:
            raise TranscriptionError(
                "FakeAI has no configured transcript; use text fallback or inject one"
            )
        return self.transcription_text

    def advance_reflection(
        self,
        messages: list[ConversationMessage],
        current_draft: ExperienceDraft | None,
        question_count: int,
    ) -> ReflectionAdvanceResult:
        if question_count == 0:
            return ReflectionAdvanceResult(
                ready_for_confirmation=False,
                next_question="后来发生了什么？你的调整带来了什么变化？",
            )
        if question_count == 1:
            return ReflectionAdvanceResult(
                ready_for_confirmation=False,
                next_question="回头看，哪里做得好、哪里还不理想，后来的人最需要注意什么？",
            )
        return ReflectionAdvanceResult(
            ready_for_confirmation=True,
            draft=self._build_draft(messages),
        )

    def rank_experiences(
        self,
        concern: str,
        candidates: list[ExperienceCandidate],
    ) -> ExperienceMatch | None:
        return rank_experiences_locally(concern, candidates)

    def _build_draft(self, messages: Sequence[ConversationMessage]) -> ExperienceDraft:
        marker = next((message for message in messages if message.kind == MessageKind.marker), None)
        answers = [message for message in messages if message.kind == MessageKind.answer]
        sources = {field: [] for field in (
            "context",
            "action_and_reason",
            "observed_result",
            "went_well",
            "shortcomings",
            "things_to_note",
            "open_question",
        )}

        values: dict[str, str | None] = {field: None for field in sources}
        if marker and "三个孩子" in marker.text and "自由选书" in marker.text:
            values["context"] = "亲子共读活动中，三个孩子一直站在门口。"
            sources["context"] = [marker.turn_id]
            values["action_and_reason"] = "看到孩子没有进入活动，我先改成自由选书。"
            sources["action_and_reason"] = [marker.turn_id]

        if answers:
            values["observed_result"] = answers[0].text
            sources["observed_result"] = [answers[0].turn_id]

        if len(answers) > 1:
            reflection = answers[1]
            text = reflection.text
            if any(token in text for token in ("做得好", "降低", "进入", "参与")):
                values["went_well"] = text
                sources["went_well"] = [reflection.turn_id]
            if any(token in text for token in ("不足", "不理想", "分散", "缺少")):
                values["shortcomings"] = text
                sources["shortcomings"] = [reflection.turn_id]
            if any(token in text for token in ("下次", "提醒", "注意", "提前")):
                values["things_to_note"] = text
                sources["things_to_note"] = [reflection.turn_id]
            if any(token in text for token in ("不确定", "疑问", "还不知道")):
                values["open_question"] = text
                sources["open_question"] = [reflection.turn_id]

        return ExperienceDraft(**values, source_turn_ids=sources, warnings=[])
