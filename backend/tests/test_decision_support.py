from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select

from app.ai import FakeAIProvider, ProviderTimeoutError
from app.core.config import Settings
from app.core.errors import AppError
from app.core.logging import LOGGER_NAME
from app.main import create_app
from app.models import CaptureSession, Experience
from app.seed import seed_experiences


CONCERN = "现场很热闹，但几个孩子一直站在门口，我不知道该继续围坐还是让他们自由选书"
MATCH_ID = "00000000-0000-4000-8000-000000000501"
MATCH_ACTION = "我把统一围坐改成自由选书，希望先降低他们参与的门槛。"
MATCH_RESULT = "孩子后来走进来翻书，但现场变得比较分散。"
MATCH_SHORTCOMING = "自由选书后没有及时准备重新收拢大家的方法。"
MATCH_NOTE = "提前准备自由选择之后的收拢环节。"


def _seed(client: TestClient) -> None:
    with client.app.state.session_factory() as db:
        assert seed_experiences(db) in {0, 6}


def _counts(client: TestClient) -> tuple[int, int]:
    with client.app.state.session_factory() as db:
        return (
            db.scalar(select(func.count()).select_from(CaptureSession)) or 0,
            db.scalar(select(func.count()).select_from(Experience)) or 0,
        )


def test_text_decision_support_is_sourced_and_stateless(client: TestClient) -> None:
    _seed(client)
    before = _counts(client)

    response = client.post(
        "/api/v1/decision-support",
        data={"activity_name": " 亲子共读活动 ", "text": f" {CONCERN} "},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["activity_name"] == "亲子共读活动"
    assert body["concern_transcript"] == CONCERN
    assert body["understanding"] == CONCERN
    assert body["match"]["experience"]["id"] == MATCH_ID
    assert body["match"]["experience"]["contributor_name"] == "演示贡献者甲"
    assert 1 <= len(body["considerations"]) <= 2
    assert all(
        item["basis_experience_id"] == MATCH_ID
        for item in body["considerations"]
    )
    assert body["question_to_consider"] == "你的现场与这条经验有哪些不同？"
    assert _counts(client) == before
    assert set(inspect(client.app.state.engine).get_table_names()) == {
        "capture_sessions",
        "experiences",
    }


def test_decision_support_input_contract_and_openapi(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/decision-support" in paths

    missing = client.post(
        "/api/v1/decision-support",
        data={"activity_name": "亲子共读活动"},
    )
    assert missing.status_code == 400
    assert missing.json()["error"]["code"] == "INPUT_REQUIRED"

    both = client.post(
        "/api/v1/decision-support",
        data={"activity_name": "亲子共读活动", "text": "困扰"},
        files={"audio": ("concern.webm", BytesIO(b"audio"), "audio/webm")},
    )
    assert both.status_code == 400
    assert both.json()["error"]["code"] == "INPUT_REQUIRED"

    for payload in (
        {"activity_name": " ", "text": "困扰"},
        {"activity_name": "亲子共读活动", "text": " "},
    ):
        invalid = client.post("/api/v1/decision-support", data=payload)
        assert invalid.status_code == 400
        assert invalid.json()["error"]["code"] == "INVALID_INPUT"

    with pytest.raises(Exception, match="DEMO_ORG_CONTEXT"):
        Settings(demo_org_context=" ")


class SupportSpy(FakeAIProvider):
    def __init__(self, transcription_text: str | None = None) -> None:
        super().__init__(transcription_text)
        self.support_calls = 0

    def support_decision(self, organization_context, concern, matched_experience):
        self.support_calls += 1
        return super().support_decision(
            organization_context, concern, matched_experience
        )


def test_no_match_skips_generation_and_unconfirmed_session_is_not_a_basis(
    settings,
) -> None:
    provider = SupportSpy()
    with TestClient(create_app(settings=settings, ai_provider=provider)) as client:
        marker = client.post(
            "/api/v1/capture-sessions",
            data={"activity_name": "亲子共读活动", "text": CONCERN},
        )
        assert marker.status_code == 201
        before = _counts(client)

        response = client.post(
            "/api/v1/decision-support",
            data={"activity_name": "亲子共读活动", "text": CONCERN},
        )

        assert response.status_code == 200
        assert response.json() == {
            "activity_name": "亲子共读活动",
            "concern_transcript": CONCERN,
            "understanding": CONCERN,
            "match": None,
            "considerations": [],
            "question_to_consider": None,
        }
        assert provider.support_calls == 0
        assert _counts(client) == before


class ResultProvider(FakeAIProvider):
    def __init__(self, result=None, error: Exception | None = None) -> None:
        super().__init__()
        self.result = result
        self.error = error

    def support_decision(self, organization_context, concern, matched_experience):
        if self.error is not None:
            raise self.error
        return self.result


def _request_with_provider(settings, provider: FakeAIProvider) -> dict:
    with TestClient(create_app(settings=settings, ai_provider=provider)) as client:
        _seed(client)
        response = client.post(
            "/api/v1/decision-support",
            data={"activity_name": "亲子共读活动", "text": CONCERN},
        )
        assert response.status_code == 200, response.text
        return response.json()


def test_valid_provider_result_is_limited_and_bound_by_service(settings) -> None:
    provider = ResultProvider(
        {
            "understanding": "历史经验显示孩子后来进入了活动。",
            "considerations": [
                {
                    "direction": MATCH_ACTION,
                    "tradeoff": MATCH_SHORTCOMING,
                    "basis_fields": ["action_and_reason", "shortcomings"],
                },
                {
                    "direction": MATCH_NOTE,
                    "tradeoff": None,
                    "basis_fields": ["things_to_note"],
                },
            ],
            "question_to_consider": "这些孩子是否理解活动规则？",
        }
    )

    body = _request_with_provider(settings, provider)

    assert body["understanding"] == CONCERN
    assert len(body["considerations"]) == 2
    assert {item["basis_experience_id"] for item in body["considerations"]} == {
        MATCH_ID
    }
    assert all("basis_fields" not in item for item in body["considerations"])


def test_provider_failure_and_invalid_sources_use_field_only_fallback(settings) -> None:
    invalid_results = [
        ResultProvider(error=RuntimeError("provider failed with raw output")),
        ResultProvider(
            {
                "understanding": "理解",
                "considerations": [
                    {
                        "direction": "给孩子递书并邀请坐到边位。",
                        "tradeoff": None,
                        "basis_fields": ["action_and_reason"],
                    }
                ],
                "question_to_consider": None,
            }
        ),
        ResultProvider(
            {
                "understanding": "理解",
                "considerations": [
                    {
                        "direction": MATCH_ACTION,
                        "tradeoff": "现场可能会更分散。",
                        "basis_fields": ["action_and_reason", "shortcomings"],
                    }
                ],
                "question_to_consider": None,
            }
        ),
        ResultProvider(
            {
                "understanding": "理解",
                "considerations": [
                    {
                        "direction": MATCH_ACTION,
                        "tradeoff": MATCH_SHORTCOMING,
                        "basis_fields": [
                            "action_and_reason",
                            "shortcomings",
                            "context",
                        ],
                    }
                ],
                "question_to_consider": None,
            }
        ),
        ResultProvider(
            {
                "understanding": "理解",
                "considerations": [
                    {
                        "direction": "非法字段来源",
                        "tradeoff": None,
                        "basis_fields": ["not_an_experience_field"],
                    }
                ],
                "question_to_consider": None,
            }
        ),
        ResultProvider(
            {
                "understanding": "理解",
                "considerations": [],
                "question_to_consider": None,
                "raw_model_output": "secret",
            }
        ),
        ResultProvider(
            {
                "understanding": "理解",
                "considerations": [
                    {
                        "direction": f"方向 {index}",
                        "tradeoff": None,
                        "basis_fields": ["context"],
                    }
                    for index in range(3)
                ],
                "question_to_consider": None,
            }
        ),
    ]

    for provider in invalid_results:
        body = _request_with_provider(settings, provider)
        experience = body["match"]["experience"]
        assert body["understanding"] == CONCERN
        assert body["considerations"] == [
            {
                "direction": experience["action_and_reason"],
                "tradeoff": experience["shortcomings"],
                "basis_experience_id": MATCH_ID,
            }
        ]
        assert body["question_to_consider"] == "你的现场与这条经验有哪些不同？"
        serialized = str(body)
        assert "raw_model_output" not in serialized
        assert "provider failed with raw output" not in serialized


def test_audio_decision_support_transcribes_and_always_cleans(settings) -> None:
    provider = FakeAIProvider(transcription_text=CONCERN)
    with TestClient(create_app(settings=settings, ai_provider=provider)) as client:
        _seed(client)
        response = client.post(
            "/api/v1/decision-support",
            data={"activity_name": "亲子共读活动"},
            files={
                "audio": (
                    "../../client-name.webm",
                    BytesIO(b"safe-audio"),
                    "audio/webm",
                )
            },
        )

        assert response.status_code == 200, response.text
        assert response.json()["concern_transcript"] == CONCERN
        assert str(settings.audio_storage_dir) not in response.text
        assert "client-name.webm" not in response.text
        assert list(client.app.state.audio_storage.root.iterdir()) == []

    failing_provider = FakeAIProvider()
    with TestClient(
        create_app(settings=settings, ai_provider=failing_provider)
    ) as client:
        failed = client.post(
            "/api/v1/decision-support",
            data={"activity_name": "亲子共读活动"},
            files={"audio": ("failed.wav", BytesIO(b"audio"), "audio/wav")},
        )
        assert failed.status_code == 502
        assert failed.json()["error"] == {
            "code": "TRANSCRIPTION_FAILED",
            "message": "语音转写失败，请重试或改用文字描述。",
            "retryable": True,
        }
        assert list(client.app.state.audio_storage.root.iterdir()) == []


def test_decision_support_audio_validation_leaves_no_files(
    settings, tmp_path
) -> None:
    with TestClient(create_app(settings=settings)) as client:
        unsupported = client.post(
            "/api/v1/decision-support",
            data={"activity_name": "亲子共读活动"},
            files={"audio": ("note.txt", BytesIO(b"audio"), "text/plain")},
        )
        assert unsupported.status_code == 400
        assert unsupported.json()["error"]["code"] == "UNSUPPORTED_AUDIO_TYPE"
        assert list(client.app.state.audio_storage.root.iterdir()) == []

    small_settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'small.db').as_posix()}",
        audio_storage_dir=str(tmp_path / "small-audio"),
        max_audio_bytes=4,
        ai_provider="fake",
    )
    with TestClient(create_app(settings=small_settings)) as client:
        oversized = client.post(
            "/api/v1/decision-support",
            data={"activity_name": "亲子共读活动"},
            files={"audio": ("note.mp3", BytesIO(b"12345"), "audio/mpeg")},
        )
        assert oversized.status_code == 400
        assert oversized.json()["error"]["code"] == "AUDIO_TOO_LARGE"
        assert list(client.app.state.audio_storage.root.iterdir()) == []


def test_startup_cleanup_removes_orphan_decision_support_audio(settings) -> None:
    audio_root = settings.audio_storage_dir
    orphan = Path(audio_root) / "decision-support-orphan"
    orphan.mkdir(parents=True)
    (orphan / "orphan.webm").write_bytes(b"orphan")

    with TestClient(create_app(settings=settings)) as client:
        assert not orphan.exists()
        assert client.app.state.startup_cleanup_result.deleted == 1


class TimeoutTranscriptionProvider(FakeAIProvider):
    def transcribe(self, audio_path: str) -> str:
        raise ProviderTimeoutError("secret timeout provider response")


def test_audio_timeout_cleans_and_cleanup_failure_is_storage_error(
    settings, monkeypatch
) -> None:
    with TestClient(
        create_app(settings=settings, ai_provider=TimeoutTranscriptionProvider())
    ) as client:
        timed_out = client.post(
            "/api/v1/decision-support",
            data={"activity_name": "亲子共读活动"},
            files={"audio": ("timeout.webm", BytesIO(b"audio"), "audio/webm")},
        )
        assert timed_out.status_code == 504
        assert timed_out.json()["error"]["code"] == "AI_TIMEOUT"
        assert list(client.app.state.audio_storage.root.iterdir()) == []

    provider = FakeAIProvider(transcription_text=CONCERN)
    with TestClient(create_app(settings=settings, ai_provider=provider)) as client:
        monkeypatch.setattr(
            client.app.state.audio_storage,
            "delete_file",
            lambda _: (_ for _ in ()).throw(
                AppError(500, "STORAGE_ERROR", "临时音频无法清理。")
            ),
        )
        cleanup_failed = client.post(
            "/api/v1/decision-support",
            data={"activity_name": "亲子共读活动"},
            files={"audio": ("cleanup.wav", BytesIO(b"audio"), "audio/wav")},
        )
        assert cleanup_failed.status_code == 500
        assert cleanup_failed.json()["error"]["code"] == "STORAGE_ERROR"
        assert str(settings.audio_storage_dir) not in cleanup_failed.text


def test_decision_support_response_and_logs_hide_sensitive_context(
    settings, caplog
) -> None:
    secret_key = "decision-support-secret-key"
    secret_context = "private-internal-organization-prompt"
    secret_transcript = "private-full-concern-transcript"
    settings.ai_api_key = secret_key
    settings.demo_org_context = secret_context
    provider = FakeAIProvider(transcription_text=secret_transcript)
    logger = logging.getLogger(LOGGER_NAME)
    logger.addHandler(caplog.handler)
    try:
        with TestClient(create_app(settings=settings, ai_provider=provider)) as client:
            response = client.post(
                "/api/v1/decision-support",
                data={"activity_name": "没有候选的活动"},
                files={"audio": ("private.mp3", BytesIO(b"audio"), "audio/mpeg")},
            )
            assert response.status_code == 200
            assert secret_key not in response.text
            assert secret_context not in response.text
            assert "file://" not in response.text
    finally:
        logger.removeHandler(caplog.handler)

    assert secret_key not in caplog.text
    assert secret_context not in caplog.text
    assert secret_transcript not in caplog.text
    assert "private.mp3" not in caplog.text
