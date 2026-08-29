from __future__ import annotations

import json
import socket
from collections.abc import Callable, Mapping
from http import HTTPStatus
from pathlib import Path
from typing import Any, Protocol, TypeVar

from pydantic import ValidationError

from app.ai import (
    AIProvider,
    ProviderInvalidOutputError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    TranscriptionError,
)
from app.core.config import Settings
from app.schemas import (
    ConversationMessage,
    DRAFT_TEXT_FIELDS,
    ExperienceCandidate,
    ExperienceDraft,
    ExperienceMatch,
    ExperienceRankingResult,
    ReflectionAdvanceResult,
)


REFLECTION_SYSTEM_PROMPT = """你是“经验捕手”的复盘助手。你只能整理贡献者在完整会话中明确表达的个人经验。

必须遵守：
1. 读取所有消息，后出现的明确纠正优先；不得把初始 marker 直接当成完整 context。
2. 不得编造缺失事实，不得把个人经验提升为普遍规律、最佳实践或组织规则。
3. 优先补齐 context、action_and_reason、observed_result，再询问 went_well、shortcomings、things_to_note、open_question。
4. 每次最多返回一个简短、现场化的问题；目标在两轮内成稿，服务端硬上限为三问。
5. 未知字段必须是 null；open_question 仅在贡献者明确表达不确定时填写。
6. 草稿的 source_turn_ids 只能引用输入中给出的合法 turn_id；无法找到来源时保持空数组。
7. 有冲突且无法继续追问时，在 warnings 中记录，不得自行选择一个说法。
8. 只返回一个符合给定 Schema 的 JSON 对象，不要 Markdown、代码围栏、解释或额外字段。
"""

RETRIEVAL_SYSTEM_PROMPT = """你是“经验捕手”的相似经验排序器。

必须遵守：
1. 只能从输入 candidates 中选择至多一条经验，不能生成新经验或修改候选内容。
2. 根据 concern 与候选中明确记录的现场、行动、结果和复盘判断选择最相似项。
3. why_similar 只能解释 concern 与所选候选中实际存在的相似点，不得输出建议、普遍规律或组织结论。
4. 没有足够相似项时返回 {"match": null}。
5. 只返回符合给定 Schema 的 JSON 对象，不要 Markdown、代码围栏、解释或额外字段。
"""


class DashScopeClient(Protocol):
    def transcribe(
        self, *, audio_uri: str, model: str, timeout_seconds: int
    ) -> Any: ...

    def generate(
        self,
        *,
        messages: list[dict[str, str]],
        model: str,
        timeout_seconds: int,
    ) -> Any: ...


class DashScopeSDKClient:
    """Thin boundary around the official SDK so tests never need the network."""

    def __init__(self, *, api_key: str, base_url: str) -> None:
        self._api_key = api_key
        self._base_url = base_url

    def _sdk(self) -> Any:
        try:
            import dashscope
        except ImportError as exc:  # pragma: no cover - guarded by requirements
            raise ProviderUnavailableError(
                "DashScope SDK is not installed", retryable=False
            ) from exc
        dashscope.base_http_api_url = self._base_url
        return dashscope

    def transcribe(
        self, *, audio_uri: str, model: str, timeout_seconds: int
    ) -> Any:
        dashscope = self._sdk()
        return dashscope.MultiModalConversation.call(
            api_key=self._api_key,
            model=model,
            messages=[{"role": "user", "content": [{"audio": audio_uri}]}],
            result_format="message",
            asr_options={"enable_itn": True},
            request_timeout=timeout_seconds,
        )

    def generate(
        self,
        *,
        messages: list[dict[str, str]],
        model: str,
        timeout_seconds: int,
    ) -> Any:
        dashscope = self._sdk()
        return dashscope.Generation.call(
            api_key=self._api_key,
            model=model,
            messages=messages,
            result_format="message",
            response_format={"type": "json_object"},
            enable_thinking=False,
            request_timeout=timeout_seconds,
        )


T = TypeVar("T")


def _value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _sequence_item(value: Any, key: str, index: int = 0) -> Any:
    sequence = _value(value, key)
    if not isinstance(sequence, (list, tuple)) or len(sequence) <= index:
        raise ProviderInvalidOutputError("provider response shape is invalid")
    return sequence[index]


def _response_status(response: Any) -> int:
    status = _value(response, "status_code")
    try:
        return int(status)
    except (TypeError, ValueError) as exc:
        raise ProviderInvalidOutputError("provider response has no status") from exc


def _provider_error(status: int, code: Any = None) -> Exception:
    normalized_code = str(code or "").lower()
    if status in {408, 504} or "timeout" in normalized_code:
        return ProviderTimeoutError("provider request timed out")
    if status == 429 or status >= 500:
        return ProviderUnavailableError(
            "provider service is temporarily unavailable", retryable=True
        )
    return ProviderUnavailableError("provider rejected the request", retryable=False)


def _exception_error(exc: Exception) -> Exception:
    if isinstance(
        exc,
        (
            ProviderTimeoutError,
            ProviderUnavailableError,
            ProviderInvalidOutputError,
            TranscriptionError,
        ),
    ):
        return exc
    timeout_exception = isinstance(exc, (TimeoutError, socket.timeout)) or any(
        "timeout" in exception_type.__name__.lower()
        for exception_type in type(exc).__mro__
    )
    if timeout_exception:
        return ProviderTimeoutError("provider request timed out")
    status = getattr(exc, "status_code", None)
    try:
        if status is not None:
            return _provider_error(int(status), getattr(exc, "code", None))
    except (TypeError, ValueError):
        pass
    if isinstance(exc, (ConnectionError, OSError)):
        return ProviderUnavailableError(
            "provider connection failed", retryable=True
        )
    return ProviderUnavailableError("provider request failed", retryable=False)


class DashScopeAIProvider(AIProvider):
    def __init__(self, settings: Settings, client: DashScopeClient | None = None) -> None:
        self._client = client or DashScopeSDKClient(
            api_key=settings.ai_api_key, base_url=settings.ai_base_url
        )
        self._model = settings.ai_model
        self._asr_model = settings.ai_asr_model
        self._timeout_seconds = settings.ai_timeout_seconds
        self._max_retries = settings.ai_max_retries

    def _run(
        self,
        request: Callable[[], Any],
        parser: Callable[[Any], T],
        *,
        retry_parse_errors: tuple[type[Exception], ...],
    ) -> T:
        for attempt in range(self._max_retries + 1):
            try:
                response = request()
                status = _response_status(response)
                if status != HTTPStatus.OK:
                    raise _provider_error(status, _value(response, "code"))
                return parser(response)
            except Exception as exc:
                error = _exception_error(exc)
                can_retry = (
                    isinstance(error, retry_parse_errors)
                    or isinstance(error, ProviderTimeoutError)
                    or (
                        isinstance(error, ProviderUnavailableError)
                        and error.retryable
                    )
                )
                if can_retry and attempt < self._max_retries:
                    continue
                raise error from exc
        raise AssertionError("retry loop must return or raise")

    def transcribe(self, audio_path: str) -> str:
        try:
            audio_uri = Path(audio_path).expanduser().resolve(strict=True).as_uri()
        except (OSError, ValueError) as exc:
            raise TranscriptionError("audio file is unavailable") from exc

        def parse(response: Any) -> str:
            output = _value(response, "output")
            choice = _sequence_item(output, "choices")
            message = _value(choice, "message")
            content = _sequence_item(message, "content")
            transcript = _value(content, "text")
            if not isinstance(transcript, str) or not transcript.strip():
                raise TranscriptionError("provider returned an empty transcript")
            return transcript.strip()

        try:
            return self._run(
                lambda: self._client.transcribe(
                    audio_uri=audio_uri,
                    model=self._asr_model,
                    timeout_seconds=self._timeout_seconds,
                ),
                parse,
                retry_parse_errors=(TranscriptionError, ProviderInvalidOutputError),
            )
        except ProviderTimeoutError:
            raise
        except TranscriptionError:
            raise
        except Exception as exc:
            raise TranscriptionError("provider transcription failed") from exc

    def advance_reflection(
        self,
        messages: list[ConversationMessage],
        current_draft: ExperienceDraft | None,
        question_count: int,
    ) -> ReflectionAdvanceResult:
        valid_turn_ids = {message.turn_id for message in messages}
        allowed_manual_edit = bool(
            current_draft
            and any(
                "manual_edit" in sources
                for sources in current_draft.source_turn_ids.values()
            )
        )
        payload = {
            "question_count": question_count,
            "valid_turn_ids": sorted(valid_turn_ids),
            "messages": [message.model_dump(mode="json") for message in messages],
            "current_draft": (
                current_draft.model_dump(mode="json") if current_draft else None
            ),
            "response_schema": ReflectionAdvanceResult.model_json_schema(),
        }
        provider_messages = [
            {"role": "system", "content": REFLECTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            },
        ]

        def parse(response: Any) -> ReflectionAdvanceResult:
            output = _value(response, "output")
            choice = _sequence_item(output, "choices")
            message = _value(choice, "message")
            content = _value(message, "content")
            if not isinstance(content, str) or not content.strip():
                raise ProviderInvalidOutputError("model returned no JSON content")
            try:
                raw = json.loads(content)
                result = ReflectionAdvanceResult.model_validate(raw)
            except (json.JSONDecodeError, ValidationError, TypeError) as exc:
                raise ProviderInvalidOutputError(
                    "model response does not match the reflection schema"
                ) from exc
            if result.next_question is not None and not result.next_question.strip():
                raise ProviderInvalidOutputError("model returned an empty question")
            if result.draft is not None:
                unknown_fields = set(result.draft.source_turn_ids) - set(
                    DRAFT_TEXT_FIELDS
                )
                if unknown_fields:
                    raise ProviderInvalidOutputError(
                        "model returned unknown source fields"
                    )
                allowed_sources = valid_turn_ids | (
                    {"manual_edit"} if allowed_manual_edit else set()
                )
                returned_sources = {
                    source
                    for sources in result.draft.source_turn_ids.values()
                    for source in sources
                }
                if not returned_sources <= allowed_sources:
                    raise ProviderInvalidOutputError(
                        "model referenced a turn outside the conversation"
                    )
                for field in DRAFT_TEXT_FIELDS:
                    field_value = getattr(result.draft, field)
                    field_sources = result.draft.source_turn_ids.get(field, [])
                    if field_value is not None and not field_sources:
                        raise ProviderInvalidOutputError(
                            "model returned a fact without a conversation source"
                        )
            return result

        return self._run(
            lambda: self._client.generate(
                messages=provider_messages,
                model=self._model,
                timeout_seconds=self._timeout_seconds,
            ),
            parse,
            retry_parse_errors=(ProviderInvalidOutputError,),
        )

    def rank_experiences(
        self,
        concern: str,
        candidates: list[ExperienceCandidate],
    ) -> ExperienceMatch | None:
        if not candidates:
            return None
        limited_candidates = candidates[:20]
        candidate_ids = {candidate.id for candidate in limited_candidates}
        payload = {
            "concern": concern,
            "candidate_ids": sorted(candidate_ids),
            "candidates": [
                candidate.model_dump(mode="json") for candidate in limited_candidates
            ],
            "response_schema": ExperienceRankingResult.model_json_schema(),
        }
        provider_messages = [
            {"role": "system", "content": RETRIEVAL_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            },
        ]

        def parse(response: Any) -> ExperienceMatch | None:
            output = _value(response, "output")
            choice = _sequence_item(output, "choices")
            message = _value(choice, "message")
            content = _value(message, "content")
            if not isinstance(content, str) or not content.strip():
                raise ProviderInvalidOutputError("model returned no ranking JSON")
            try:
                raw = json.loads(content)
                result = ExperienceRankingResult.model_validate(raw)
            except (json.JSONDecodeError, ValidationError, TypeError) as exc:
                raise ProviderInvalidOutputError(
                    "model response does not match the ranking schema"
                ) from exc
            if result.match is not None and result.match.experience_id not in candidate_ids:
                raise ProviderInvalidOutputError(
                    "model selected an experience outside candidates"
                )
            return result.match

        return self._run(
            lambda: self._client.generate(
                messages=provider_messages,
                model=self._model,
                timeout_seconds=self._timeout_seconds,
            ),
            parse,
            retry_parse_errors=(ProviderInvalidOutputError,),
        )


def build_ai_provider(settings: Settings) -> AIProvider:
    if settings.ai_provider == "fake":
        from app.ai import FakeAIProvider

        return FakeAIProvider()
    if settings.ai_provider == "dashscope":
        return DashScopeAIProvider(settings)
    raise ValueError(f"Unsupported AI provider: {settings.ai_provider}")
