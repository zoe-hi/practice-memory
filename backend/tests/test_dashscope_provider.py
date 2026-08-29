from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.ai import (
    FakeAIProvider,
    ProviderInvalidOutputError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    TranscriptionError,
)
from app.core.config import Settings
from app.dashscope_provider import DashScopeAIProvider, DashScopeSDKClient
from app.main import create_app
from app.schemas import (
    ConversationMessage,
    DRAFT_TEXT_FIELDS,
    ExperienceCandidate,
    MessageKind,
    MessageRole,
    MessageSource,
)
from tests.conftest import create_marker


def _settings(**updates: Any) -> Settings:
    values = {
        "ai_provider": "dashscope",
        "ai_api_key": "test-secret-key",
        "ai_base_url": "https://dashscope.aliyuncs.com/api/v1",
        "ai_model": "qwen-plus",
        "ai_asr_model": "qwen3-asr-flash",
        "ai_timeout_seconds": 12,
        "ai_max_retries": 1,
    }
    values.update(updates)
    return Settings(**values)


def _ok_asr(text: str) -> dict[str, Any]:
    return {
        "status_code": 200,
        "output": {"choices": [{"message": {"content": [{"text": text}]}}]},
    }


def _ok_generation(content: str) -> dict[str, Any]:
    return {
        "status_code": 200,
        "output": {"choices": [{"message": {"content": content}}]},
    }


def _ok_generation_blocks(content: str) -> dict[str, Any]:
    return {
        "status_code": 200,
        "output": {"choices": [{"message": {"content": [{"text": content}]}}]},
    }


class StubDashScopeClient:
    def __init__(
        self,
        *,
        transcription_results: list[Any] | None = None,
        generation_results: list[Any] | None = None,
    ) -> None:
        self.transcription_results = list(transcription_results or [])
        self.generation_results = list(generation_results or [])
        self.transcription_calls: list[dict[str, Any]] = []
        self.generation_calls: list[dict[str, Any]] = []

    @staticmethod
    def _next(results: list[Any]) -> Any:
        value = results.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    def transcribe(self, **kwargs: Any) -> Any:
        self.transcription_calls.append(kwargs)
        return self._next(self.transcription_results)

    def generate(self, **kwargs: Any) -> Any:
        self.generation_calls.append(kwargs)
        return self._next(self.generation_results)


def _marker() -> ConversationMessage:
    return ConversationMessage(
        turn_id="turn-marker",
        role=MessageRole.user,
        kind=MessageKind.marker,
        text="三个孩子站在门口，我改成了自由选书。",
        source=MessageSource.text,
        created_at=datetime(2026, 8, 29, tzinfo=timezone.utc),
    )


def _ready_json(source_id: str = "turn-marker") -> str:
    sources = {field: [] for field in DRAFT_TEXT_FIELDS}
    sources["context"] = [source_id]
    return json.dumps(
        {
            "ready_for_confirmation": True,
            "next_question": None,
            "draft": {
                "context": "三个孩子站在活动入口。",
                "action_and_reason": None,
                "observed_result": None,
                "went_well": None,
                "shortcomings": None,
                "things_to_note": None,
                "open_question": None,
                "source_turn_ids": sources,
                "warnings": [],
            },
        },
        ensure_ascii=False,
    )


def test_dashscope_configuration_is_strict() -> None:
    assert _settings().ai_provider == "dashscope"
    with pytest.raises(ValidationError, match="AI_API_KEY"):
        Settings(ai_provider="dashscope", ai_api_key="")
    with pytest.raises(ValidationError, match="AI_BASE_URL"):
        _settings(ai_base_url="http://dashscope.example/api/v1")
    with pytest.raises(ValidationError, match="AI_PROVIDER"):
        Settings(ai_provider="unknown")
    with pytest.raises(ValidationError, match="less than or equal to 1"):
        _settings(ai_max_retries=2)


def test_application_builds_configured_provider(tmp_path: Path) -> None:
    settings = _settings(
        database_url=f"sqlite:///{(tmp_path / 'app.db').as_posix()}",
        audio_storage_dir=str(tmp_path / "audio"),
    )
    with TestClient(create_app(settings=settings)) as client:
        assert isinstance(client.app.state.ai_provider, DashScopeAIProvider)
        assert client.get("/api/v1/health").status_code == 200


def test_official_sdk_adapter_receives_timeout_and_json_mode(monkeypatch) -> None:
    import dashscope

    calls: dict[str, dict[str, Any]] = {}

    def fake_asr(**kwargs: Any) -> dict[str, Any]:
        calls["asr"] = kwargs
        return _ok_asr("转写")

    def fake_generation(**kwargs: Any) -> dict[str, Any]:
        calls["generation"] = kwargs
        return _ok_generation(
            '{"ready_for_confirmation":false,"next_question":"后来怎么样？","draft":null}'
        )

    monkeypatch.setattr(
        dashscope.MultiModalConversation, "call", staticmethod(fake_asr)
    )
    monkeypatch.setattr(dashscope.Generation, "call", staticmethod(fake_generation))
    adapter = DashScopeSDKClient(
        api_key="adapter-secret", base_url="https://example.com/api/v1"
    )

    adapter.transcribe(
        audio_uri="file:///tmp/marker.wav",
        model="qwen3-asr-flash",
        timeout_seconds=37,
    )
    adapter.generate(
        messages=[{"role": "user", "content": "{}"}],
        model="qwen-plus",
        timeout_seconds=37,
    )

    assert dashscope.base_http_api_url == "https://example.com/api/v1"
    assert calls["asr"]["request_timeout"] == 37
    assert calls["asr"]["asr_options"] == {"enable_itn": True}
    assert calls["generation"]["request_timeout"] == 37
    assert calls["generation"]["response_format"] == {"type": "json_object"}
    assert calls["generation"]["enable_thinking"] is False


def test_transcription_uses_safe_file_uri_and_configured_models(
    tmp_path: Path,
) -> None:
    audio = tmp_path / "marker.wav"
    audio.write_bytes(b"audio")
    client = StubDashScopeClient(transcription_results=[_ok_asr("  转写结果  ")])
    provider = DashScopeAIProvider(_settings(), client=client)

    assert provider.transcribe(str(audio)) == "转写结果"
    call = client.transcription_calls[0]
    assert call["audio_uri"] == audio.resolve().as_uri()
    assert call["audio_uri"].startswith("file:")
    assert call["model"] == "qwen3-asr-flash"
    assert call["timeout_seconds"] == 12
    assert "test-secret-key" not in json.dumps(call)


def test_transcription_retries_transient_and_empty_results(tmp_path: Path) -> None:
    audio = tmp_path / "marker.webm"
    audio.write_bytes(b"audio")
    transient = StubDashScopeClient(
        transcription_results=[
            {"status_code": 503, "code": "ServiceUnavailable"},
            _ok_asr("成功"),
        ]
    )
    assert DashScopeAIProvider(_settings(), client=transient).transcribe(str(audio)) == "成功"
    assert len(transient.transcription_calls) == 2

    empty = StubDashScopeClient(
        transcription_results=[_ok_asr(""), _ok_asr("  ")]
    )
    with pytest.raises(TranscriptionError):
        DashScopeAIProvider(_settings(), client=empty).transcribe(str(audio))
    assert len(empty.transcription_calls) == 2


def test_authentication_is_not_retried_and_timeout_is_retried(
    tmp_path: Path,
) -> None:
    audio = tmp_path / "marker.mp3"
    audio.write_bytes(b"audio")
    auth = StubDashScopeClient(
        transcription_results=[{"status_code": 401, "code": "InvalidApiKey"}]
    )
    with pytest.raises(TranscriptionError):
        DashScopeAIProvider(_settings(), client=auth).transcribe(str(audio))
    assert len(auth.transcription_calls) == 1

    timeout = StubDashScopeClient(
        transcription_results=[TimeoutError("secret detail"), TimeoutError("again")]
    )
    with pytest.raises(ProviderTimeoutError):
        DashScopeAIProvider(_settings(), client=timeout).transcribe(str(audio))
    assert len(timeout.transcription_calls) == 2


def test_reflection_sends_complete_conversation_without_internal_secrets() -> None:
    marker = _marker()
    answer = marker.model_copy(
        update={
            "turn_id": "turn-answer",
            "kind": MessageKind.answer,
            "text": "孩子后来进入了活动。",
        }
    )
    client = StubDashScopeClient(
        generation_results=[_ok_generation(_ready_json())]
    )
    provider = DashScopeAIProvider(_settings(), client=client)

    result = provider.advance_reflection([marker, answer], None, 2)
    assert result.ready_for_confirmation is True
    call = client.generation_calls[0]
    payload = json.loads(call["messages"][1]["content"])
    assert [item["turn_id"] for item in payload["messages"]] == [
        "turn-marker",
        "turn-answer",
    ]
    assert payload["question_count"] == 2
    assert payload["valid_turn_ids"] == ["turn-answer", "turn-marker"]
    serialized = json.dumps(call, ensure_ascii=False)
    assert "test-secret-key" not in serialized
    assert "audio_temp_path" not in serialized
    assert call["model"] == "qwen-plus"


@pytest.mark.parametrize(
    "response",
    [
        _ok_generation(
            "```json\n"
            '{"ready_for_confirmation":false,"next_question":"后来怎么样？","draft":null}'
            "\n```"
        ),
        _ok_generation_blocks(
            '{"ready_for_confirmation":false,"next_question":"后来怎么样？","draft":null}'
        ),
    ],
)
def test_reflection_accepts_common_json_wrappers(response: dict[str, Any]) -> None:
    client = StubDashScopeClient(generation_results=[response])
    result = DashScopeAIProvider(_settings(), client=client).advance_reflection(
        [_marker()], None, 0
    )
    assert result.ready_for_confirmation is False
    assert result.next_question == "后来怎么样？"


def test_reflection_discards_speculative_draft_while_asking() -> None:
    response = json.dumps(
        {
            "ready_for_confirmation": False,
            "next_question": "后来怎么样？",
            "draft": {
                "context": "模型提前猜测的内容",
                "unexpected_nested_shape": True,
            },
        },
        ensure_ascii=False,
    )
    client = StubDashScopeClient(generation_results=[_ok_generation(response)])
    result = DashScopeAIProvider(_settings(), client=client).advance_reflection(
        [_marker()], None, 0
    )
    assert result.ready_for_confirmation is False
    assert result.next_question == "后来怎么样？"
    assert result.draft is None


@pytest.mark.parametrize("ready_value", [None, "false", True])
def test_reflection_normalizes_common_follow_up_flag_variations(ready_value) -> None:
    response = {
        "next_question": "后来怎么样？",
        "draft": None,
    }
    if ready_value is not None:
        response["ready_for_confirmation"] = ready_value
    client = StubDashScopeClient(
        generation_results=[_ok_generation(json.dumps(response, ensure_ascii=False))]
    )

    result = DashScopeAIProvider(_settings(), client=client).advance_reflection(
        [_marker()], None, 0
    )

    assert result.ready_for_confirmation is False
    assert result.next_question == "后来怎么样？"
    assert result.draft is None


def test_reflection_allows_one_final_question_after_two_questions() -> None:
    response = json.dumps(
        {
            "ready_for_confirmation": False,
            "next_question": "还要继续问吗？",
            "draft": None,
        },
        ensure_ascii=False,
    )
    client = StubDashScopeClient(generation_results=[_ok_generation(response)])
    result = DashScopeAIProvider(_settings(), client=client).advance_reflection(
        [_marker()], None, 2
    )
    assert result.ready_for_confirmation is False
    assert result.next_question == "还要继续问吗？"
    assert len(client.generation_calls) == 1


def test_reflection_rejects_continuing_after_three_questions() -> None:
    response = json.dumps(
        {
            "ready_for_confirmation": False,
            "next_question": "不能再继续问。",
            "draft": None,
        },
        ensure_ascii=False,
    )
    client = StubDashScopeClient(
        generation_results=[_ok_generation(response), _ok_generation(response)]
    )
    with pytest.raises(ProviderInvalidOutputError):
        DashScopeAIProvider(_settings(), client=client).advance_reflection(
            [_marker()], None, 3
        )
    assert len(client.generation_calls) == 2


def test_reflection_rejects_an_all_null_final_draft() -> None:
    empty_sources = {field: [] for field in DRAFT_TEXT_FIELDS}
    empty_draft = json.dumps(
        {
            "ready_for_confirmation": True,
            "next_question": None,
            "draft": {
                **{field: None for field in DRAFT_TEXT_FIELDS},
                "source_turn_ids": empty_sources,
                "warnings": [],
            },
        },
        ensure_ascii=False,
    )
    client = StubDashScopeClient(
        generation_results=[_ok_generation(empty_draft), _ok_generation(empty_draft)]
    )

    with pytest.raises(ProviderInvalidOutputError):
        DashScopeAIProvider(_settings(), client=client).advance_reflection(
            [_marker()], None, 2
        )

    assert len(client.generation_calls) == 2


@pytest.mark.parametrize(
    "invalid_content",
    [
        "not-json",
        "```json\n{}\n```",
        json.dumps(
            {
                "ready_for_confirmation": False,
                "next_question": "后来怎么样？",
                "draft": None,
                "unexpected": True,
            }
        ),
        _ready_json("invented-turn"),
    ],
)
def test_invalid_structured_output_is_retried_once(invalid_content: str) -> None:
    client = StubDashScopeClient(
        generation_results=[
            _ok_generation(invalid_content),
            _ok_generation(invalid_content),
        ]
    )
    with pytest.raises(ProviderInvalidOutputError):
        DashScopeAIProvider(_settings(), client=client).advance_reflection(
            [_marker()], None, 0
        )
    assert len(client.generation_calls) == 2


def test_reflection_auth_failure_is_not_retried() -> None:
    client = StubDashScopeClient(
        generation_results=[{"status_code": 403, "code": "AccessDenied"}]
    )
    with pytest.raises(ProviderUnavailableError) as error:
        DashScopeAIProvider(_settings(), client=client).advance_reflection(
            [_marker()], None, 0
        )
    assert error.value.retryable is False
    assert len(client.generation_calls) == 1


class TimeoutReflectionProvider:
    def transcribe(self, audio_path: str) -> str:
        del audio_path
        raise ProviderTimeoutError("private timeout")

    def advance_reflection(self, messages, current_draft, question_count):
        del messages, current_draft, question_count
        raise ProviderTimeoutError("private timeout")

    def rank_experiences(self, concern, candidates):
        del concern, candidates
        return None


def test_provider_timeout_uses_unified_504_error(client: TestClient) -> None:
    client.app.state.ai_provider = TimeoutReflectionProvider()
    session_id = create_marker(client, text="待复盘标记")
    response = client.post(
        f"/api/v1/capture-sessions/{session_id}/start-reflection"
    )
    assert response.status_code == 504
    assert response.json() == {
        "error": {
            "code": "AI_TIMEOUT",
            "message": "AI 服务响应超时，请重试。",
            "retryable": True,
        }
    }
    assert "private timeout" not in response.text


class TimeoutTranscriptionProvider(FakeAIProvider):
    def transcribe(self, audio_path: str) -> str:
        del audio_path
        raise ProviderTimeoutError("private transcription timeout")


def test_audio_timeout_uses_504_and_privacy_cleanup(settings: Settings) -> None:
    provider = TimeoutTranscriptionProvider()
    with TestClient(create_app(settings=settings, ai_provider=provider)) as client:
        session_id = create_marker(client, text="文字标记")
        started = client.post(
            f"/api/v1/capture-sessions/{session_id}/start-reflection"
        )
        assert started.status_code == 200

        response = client.post(
            f"/api/v1/capture-sessions/{session_id}/turns",
            files={"audio": ("answer.wav", b"audio", "audio/wav")},
        )
        assert response.status_code == 504
        assert response.json()["error"]["code"] == "AI_TIMEOUT"
        assert response.json()["error"]["retryable"] is True
        assert "private transcription timeout" not in response.text
        assert not [
            path
            for path in Path(settings.audio_storage_dir).rglob("*")
            if path.is_file()
        ]


def test_background_timeout_is_persisted_as_generic_code(
    settings: Settings,
) -> None:
    with TestClient(
        create_app(settings=settings, ai_provider=TimeoutTranscriptionProvider())
    ) as client:
        created = client.post(
            "/api/v1/capture-sessions",
            files={"audio": ("marker.wav", b"audio", "audio/wav")},
        )
        assert created.status_code == 201
        session_id = created.json()["id"]
        with client.app.state.session_factory() as db:
            from app.models import CaptureSession

            session = db.get(CaptureSession, session_id)
            assert session is not None
            assert session.error_code == "AI_TIMEOUT"
            assert "private" not in (session.error_message or "")

        retried = client.post(
            f"/api/v1/capture-sessions/{session_id}/start-reflection"
        )
        assert retried.status_code == 504
        assert retried.json()["error"]["code"] == "AI_TIMEOUT"


def test_dashscope_ranking_sends_only_candidates_and_parses_match() -> None:
    client = StubDashScopeClient(
        generation_results=[
            _ok_generation(
                json.dumps(
                    {
                        "match": {
                            "experience_id": "candidate-1",
                            "why_similar": "都提到了孩子停留在门口。",
                        }
                    },
                    ensure_ascii=False,
                )
            )
        ]
    )
    candidates = [
        ExperienceCandidate(
            id="candidate-1",
            activity_name="亲子共读活动",
            context="孩子一直站在门口。",
        ),
        ExperienceCandidate(
            id="candidate-2",
            activity_name="亲子共读活动",
            context="孩子围坐阅读。",
        ),
    ]
    match = DashScopeAIProvider(_settings(), client=client).rank_experiences(
        "总有孩子站在门口", candidates
    )
    assert match is not None
    assert match.experience_id == "candidate-1"
    payload = json.loads(client.generation_calls[0]["messages"][1]["content"])
    assert payload["concern"] == "总有孩子站在门口"
    assert payload["candidate_ids"] == ["candidate-1", "candidate-2"]
    assert len(payload["candidates"]) == 2
    serialized = json.dumps(client.generation_calls[0], ensure_ascii=False)
    assert "test-secret-key" not in serialized
    assert "audio_temp_path" not in serialized


@pytest.mark.parametrize(
    "invalid_content",
    [
        "not-json",
        json.dumps(
            {
                "match": {
                    "experience_id": "outside",
                    "why_similar": "不合法",
                }
            }
        ),
    ],
)
def test_dashscope_ranking_retries_invalid_and_outside_candidate_output(
    invalid_content: str,
) -> None:
    invalid = _ok_generation(invalid_content)
    client = StubDashScopeClient(generation_results=[invalid, invalid])
    candidate = ExperienceCandidate(
        id="candidate-1", activity_name="活动", context="孩子站在门口"
    )
    with pytest.raises(ProviderInvalidOutputError):
        DashScopeAIProvider(_settings(), client=client).rank_experiences(
            "孩子在门口", [candidate]
        )
    assert len(client.generation_calls) == 2


def test_dashscope_ranking_accepts_explicit_no_match_and_caps_input() -> None:
    client = StubDashScopeClient(
        generation_results=[_ok_generation('{"match":null}')]
    )
    candidates = [
        ExperienceCandidate(
            id=f"candidate-{index:02d}", activity_name="活动", context="现场记录"
        )
        for index in range(25)
    ]
    result = DashScopeAIProvider(_settings(), client=client).rank_experiences(
        "完全不同的困扰", candidates
    )
    assert result is None
    payload = json.loads(client.generation_calls[0]["messages"][1]["content"])
    assert len(payload["candidates"]) == 20


def test_dashscope_decision_support_sends_one_experience_and_validates_sources() -> None:
    valid = json.dumps(
        {
            "understanding": "孩子一直站在门口",
            "considerations": [
                {
                    "direction": "我改成自由选书，降低进入门槛。",
                    "tradeoff": "现场变得比较分散。",
                    "basis_fields": ["action_and_reason", "shortcomings"],
                }
            ],
            "question_to_consider": "你的现场与这条经验有哪些不同？",
        },
        ensure_ascii=False,
    )
    client = StubDashScopeClient(generation_results=[_ok_generation(valid)])
    candidate = ExperienceCandidate(
        id="candidate-1",
        activity_name="亲子共读活动",
        context="几个孩子一直站在门口。",
        action_and_reason="我改成自由选书，降低进入门槛。",
        shortcomings="现场变得比较分散。",
        open_question=None,
    )

    result = DashScopeAIProvider(_settings(), client=client).support_decision(
        "本机构尊重一线工作者判断。",
        "孩子一直站在门口",
        candidate,
    )

    assert result.considerations[0].basis_fields == [
        "action_and_reason",
        "shortcomings",
    ]
    payload = json.loads(client.generation_calls[0]["messages"][1]["content"])
    assert payload["organization_context"] == "本机构尊重一线工作者判断。"
    assert payload["concern"] == "孩子一直站在门口"
    assert payload["matched_experience"]["id"] == "candidate-1"
    assert "candidates" not in payload
    assert "open_question" not in payload["allowed_basis_fields"]
    system_prompt = client.generation_calls[0]["messages"][0]["content"]
    assert "understanding 必须逐字复制 concern" in system_prompt
    assert "direction 必须逐字复制" in system_prompt
    assert "tradeoff 只能为 null，或逐字复制" in system_prompt
    serialized = json.dumps(client.generation_calls, ensure_ascii=False)
    assert "test-secret-key" not in serialized
    assert "file://" not in serialized


@pytest.mark.parametrize(
    "invalid",
    [
        "not-json",
        json.dumps(
            {
                "understanding": "理解",
                "considerations": [
                    {
                        "direction": "没有合法来源",
                        "tradeoff": None,
                        "basis_fields": ["open_question"],
                    }
                ],
                "question_to_consider": None,
            }
        ),
        json.dumps(
            {
                "understanding": "理解",
                "considerations": [],
                "question_to_consider": None,
                "extra": "forbidden",
            }
        ),
    ],
)
def test_dashscope_decision_support_retries_invalid_output_once(
    invalid: str,
) -> None:
    client = StubDashScopeClient(
        generation_results=[_ok_generation(invalid), _ok_generation(invalid)]
    )
    candidate = ExperienceCandidate(
        id="candidate-1",
        activity_name="亲子共读活动",
        context="孩子站在门口。",
    )

    with pytest.raises(ProviderInvalidOutputError):
        DashScopeAIProvider(_settings(), client=client).support_decision(
            "机构语境", "孩子在门口", candidate
        )
    assert len(client.generation_calls) == 2


@pytest.mark.skipif(
    os.getenv("RUN_REAL_AI_TESTS") != "1" or not os.getenv("AI_API_KEY"),
    reason="requires explicit RUN_REAL_AI_TESTS=1 and AI_API_KEY",
)
def test_live_dashscope_provider_smoke() -> None:
    settings = Settings(
        ai_provider="dashscope",
        ai_api_key=os.environ["AI_API_KEY"],
        ai_base_url=os.getenv(
            "AI_BASE_URL", "https://dashscope.aliyuncs.com/api/v1"
        ),
        ai_model=os.getenv("AI_MODEL", "qwen-plus"),
        ai_asr_model=os.getenv("AI_ASR_MODEL", "qwen3-asr-flash"),
    )
    provider = DashScopeAIProvider(settings)
    result = provider.advance_reflection([_marker()], None, 0)
    assert result.next_question or result.draft
    candidate = ExperienceCandidate(
        id="candidate-1",
        activity_name="亲子共读活动",
        context="几个孩子一直站在活动门口。",
    )
    match = provider.rank_experiences("总有孩子站在门口", [candidate])
    assert match is None or match.experience_id == candidate.id
    decision = provider.support_decision(
        settings.demo_org_context,
        "总有孩子站在门口",
        candidate,
    )
    assert len(decision.considerations) <= 2
