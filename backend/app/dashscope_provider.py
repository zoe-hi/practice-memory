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
    DecisionSupportAIResult,
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
5. 当输入中的 question_count 大于等于 2 时，必须立即返回最终草稿：ready_for_confirmation=true、next_question=null，绝不能继续提问。
6. 未知字段必须是 null；open_question 仅在贡献者明确表达不确定时填写。
7. 草稿的 source_turn_ids 只能引用输入中给出的合法 turn_id；无法找到来源时保持空数组。
8. 有冲突且无法继续追问时，在 warnings 中记录，不得自行选择一个说法。
9. 只返回一个符合给定 Schema 的 JSON 对象，不要 Markdown、代码围栏、解释或额外字段。

继续追问时必须使用这个精确形状，不要附带草稿：
{"ready_for_confirmation":false,"next_question":"一个简短问题","draft":null}

最终草稿必须设置 ready_for_confirmation=true、next_question=null，并返回 draft。draft 必须包含七个经验字段、source_turn_ids 和 warnings；source_turn_ids 必须是对象且包含全部七个经验字段名。请从 messages 中提取贡献者已经明确表达的内容，不要照抄空模板。每个非 null 字段必须列出支持它的合法 turn_id；真正没有表达的字段才使用 null 和空来源数组。最终草稿至少要有一个非 null 的经验字段。

特别禁止：根据人数相减推出未表达的人数；为行动补充未说过的目的或因果；为结果、不足补充未说过的原因。任何没有明确来源的信息必须保持 null。
"""

RETRIEVAL_SYSTEM_PROMPT = """你是“经验捕手”的相似经验排序器。

必须遵守：
1. 只能从输入 candidates 中选择至多一条经验，不能生成新经验或修改候选内容。
2. 根据 concern 与候选中明确记录的现场、行动、结果和复盘判断选择最相似项。
3. why_similar 只能解释 concern 与所选候选中实际存在的相似点，不得输出建议、普遍规律或组织结论。
4. 没有足够相似项时返回 {"match": null}。
5. 只返回符合给定 Schema 的 JSON 对象，不要 Markdown、代码围栏、解释或额外字段。
"""

DECISION_SUPPORT_SYSTEM_PROMPT = """你是“经验捕手”的有来源决策支持整理器。

必须遵守：
1. understanding 必须逐字复制 concern，只能整理空白和标点；不得把历史经验的结果、原因或不足写成当前事实。
2. 输出最多两个可考虑方向。direction 必须逐字复制 matched_experience.action_and_reason 或 matched_experience.things_to_note 的完整非空文本，不得改写、拼接、概括或增加例子。
3. tradeoff 只能为 null，或逐字复制 matched_experience.shortcomings 或 matched_experience.observed_result 的完整非空文本。
4. basis_fields 只能列出该条 direction 和 tradeoff 实际逐字取值的字段，不得添加无关字段。
5. 机构宗旨只用于限制语气和边界，不能作为当前事实或 direction、tradeoff 的文字来源。
6. question_to_consider 可以根据当前困扰与历史经验的差异提出，但不得把推测陈述为事实。
7. 没有依据时少输出或返回 null，不得补齐；禁止引入外部知识、新事实或具体动作。
8. 禁止使用“最佳实践”“一定应该”“组织标准答案”等权威或确定性表达；最终判断属于用户本人。
9. 不得生成经验、修改经验、选择经验 ID 或输出任何内部配置。
10. 只返回符合给定 Schema 的 JSON 对象，不要 Markdown、代码围栏、解释或额外字段。
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


def _json_object_from_content(content: Any) -> dict[str, Any]:
    """Remove common SDK/model wrappers without relaxing schema validation."""
    if isinstance(content, (list, tuple)):
        fragments: list[str] = []
        for item in content:
            text = _value(item, "text")
            if isinstance(text, str):
                fragments.append(text)
            elif isinstance(item, str):
                fragments.append(item)
        content = "".join(fragments)

    if not isinstance(content, str) or not content.strip():
        raise ProviderInvalidOutputError("model returned no JSON content")

    candidate = content.strip()
    if candidate.startswith("```"):
        first_newline = candidate.find("\n")
        if first_newline == -1:
            raise ProviderInvalidOutputError("model response does not contain JSON")
        candidate = candidate[first_newline + 1 :]
        if candidate.rstrip().endswith("```"):
            candidate = candidate.rstrip()[:-3]

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end < start:
        raise ProviderInvalidOutputError("model response does not contain a JSON object")
    try:
        raw = json.loads(candidate[start : end + 1])
    except (json.JSONDecodeError, TypeError) as exc:
        raise ProviderInvalidOutputError("model response is not valid JSON") from exc
    if not isinstance(raw, dict):
        raise ProviderInvalidOutputError("model response must be a JSON object")
    return raw


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
            try:
                raw = _json_object_from_content(content)
                next_question = raw.get("next_question")
                if (
                    question_count < 2
                    and isinstance(next_question, str)
                    and next_question.strip()
                ):
                    unknown_fields = set(raw) - {
                        "ready_for_confirmation",
                        "next_question",
                        "draft",
                    }
                    if unknown_fields:
                        raise ProviderInvalidOutputError(
                            "model returned unknown reflection fields"
                        )
                    raw = {
                        "ready_for_confirmation": False,
                        "next_question": next_question,
                        "draft": None,
                    }
                result = ReflectionAdvanceResult.model_validate(raw)
            except (ProviderInvalidOutputError, ValidationError, TypeError) as exc:
                raise ProviderInvalidOutputError(
                    "model response does not match the reflection schema"
                ) from exc
            if result.next_question is not None and not result.next_question.strip():
                raise ProviderInvalidOutputError("model returned an empty question")
            if question_count >= 2 and not result.ready_for_confirmation:
                raise ProviderInvalidOutputError(
                    "model continued after the configured reflection limit"
                )
            if result.draft is not None:
                if not any(
                    getattr(result.draft, field) is not None
                    for field in DRAFT_TEXT_FIELDS
                ):
                    raise ProviderInvalidOutputError(
                        "model returned an empty reflection draft"
                    )
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
            try:
                raw = _json_object_from_content(content)
                result = ExperienceRankingResult.model_validate(raw)
            except (ProviderInvalidOutputError, ValidationError, TypeError) as exc:
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

    def support_decision(
        self,
        organization_context: str,
        concern: str,
        matched_experience: ExperienceCandidate,
    ) -> DecisionSupportAIResult:
        allowed_fields = [
            field
            for field in DRAFT_TEXT_FIELDS
            if isinstance(getattr(matched_experience, field), str)
            and getattr(matched_experience, field).strip()
        ]
        payload = {
            "organization_context": organization_context,
            "concern": concern,
            "matched_experience": matched_experience.model_dump(mode="json"),
            "allowed_basis_fields": allowed_fields,
            "response_schema": DecisionSupportAIResult.model_json_schema(),
        }
        provider_messages = [
            {"role": "system", "content": DECISION_SUPPORT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            },
        ]

        def parse(response: Any) -> DecisionSupportAIResult:
            output = _value(response, "output")
            choice = _sequence_item(output, "choices")
            message = _value(choice, "message")
            content = _value(message, "content")
            try:
                raw = _json_object_from_content(content)
                result = DecisionSupportAIResult.model_validate(raw)
            except (ProviderInvalidOutputError, ValidationError, TypeError) as exc:
                raise ProviderInvalidOutputError(
                    "model response does not match the decision support schema"
                ) from exc
            allowed = set(allowed_fields)
            if any(
                not set(consideration.basis_fields) <= allowed
                for consideration in result.considerations
            ):
                raise ProviderInvalidOutputError(
                    "model referenced an unavailable experience field"
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


def build_ai_provider(settings: Settings) -> AIProvider:
    if settings.ai_provider == "fake":
        from app.ai import FakeAIProvider

        return FakeAIProvider()
    if settings.ai_provider == "dashscope":
        return DashScopeAIProvider(settings)
    raise ValueError(f"Unsupported AI provider: {settings.ai_provider}")
