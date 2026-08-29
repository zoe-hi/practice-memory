from fastapi.testclient import TestClient

from app.ai import FakeAIProvider
from app.models import CaptureSession
from app.schemas import (
    DRAFT_TEXT_FIELDS,
    ExperienceCandidate,
    ExperienceDraft,
    ExperienceMatch,
    ReflectionAdvanceResult,
)
from tests.conftest import advance_to_draft, create_marker


def test_fake_ai_uses_complete_conversation_and_tracks_sources(
    client: TestClient,
) -> None:
    session_id = create_marker(client)
    result = advance_to_draft(client, session_id)
    assert result["draft"]["context"] == "亲子共读活动中，三个孩子一直站在门口。"
    assert result["draft"]["observed_result"] == "孩子进来了，但现场变得比较分散。"

    detail = client.get(f"/api/v1/capture-sessions/{session_id}").json()
    assert len(detail["conversation"]) == 5
    assert [turn["kind"] for turn in detail["conversation"]] == [
        "marker",
        "question",
        "answer",
        "question",
        "answer",
    ]

    factory = client.app.state.session_factory
    with factory() as db:
        stored = db.get(CaptureSession, session_id)
        assert stored is not None
        valid_ids = {turn["turn_id"] for turn in stored.conversation_json}
        source_ids = {
            source
            for sources in stored.draft_json["source_turn_ids"].values()
            for source in sources
        }
        assert source_ids <= valid_ids


class AlwaysQuestionProvider(FakeAIProvider):
    def advance_reflection(self, messages, current_draft, question_count):
        return ReflectionAdvanceResult(
            ready_for_confirmation=False,
            next_question=f"问题 {question_count + 1}",
        )

    def rank_experiences(
        self, concern: str, candidates: list[ExperienceCandidate]
    ) -> ExperienceMatch | None:
        return None


class DraftAtHardLimitProvider(AlwaysQuestionProvider):
    def advance_reflection(self, messages, current_draft, question_count):
        if question_count < 3:
            return super().advance_reflection(messages, current_draft, question_count)
        sources = {field: [] for field in DRAFT_TEXT_FIELDS}
        sources["things_to_note"] = [messages[-1].turn_id]
        return ReflectionAdvanceResult(
            ready_for_confirmation=True,
            draft=ExperienceDraft(
                things_to_note=messages[-1].text,
                source_turn_ids=sources,
            ),
        )


def test_service_enforces_three_question_hard_limit(client: TestClient) -> None:
    client.app.state.ai_provider = AlwaysQuestionProvider()
    session_id = create_marker(client, text="一个信息不足的标记")
    client.post(f"/api/v1/capture-sessions/{session_id}/start-reflection")
    client.post(
        f"/api/v1/capture-sessions/{session_id}/turns", data={"text": "回答一"}
    )
    third_question = client.post(
        f"/api/v1/capture-sessions/{session_id}/turns", data={"text": "回答二"}
    )
    assert third_question.json()["status"] == "reflecting"

    forced_draft = client.post(
        f"/api/v1/capture-sessions/{session_id}/turns", data={"text": "回答三"}
    )
    assert forced_draft.status_code == 200
    assert forced_draft.json()["status"] == "needs_confirmation"
    assert all(value is None for value in forced_draft.json()["draft"].values())
    detail = client.get(f"/api/v1/capture-sessions/{session_id}").json()
    assert sum(turn["kind"] == "question" for turn in detail["conversation"]) == 3


def test_service_uses_provider_draft_after_third_answer(client: TestClient) -> None:
    client.app.state.ai_provider = DraftAtHardLimitProvider()
    session_id = create_marker(client, text="一个信息不足的标记")
    client.post(f"/api/v1/capture-sessions/{session_id}/start-reflection")
    client.post(
        f"/api/v1/capture-sessions/{session_id}/turns", data={"text": "回答一"}
    )
    client.post(
        f"/api/v1/capture-sessions/{session_id}/turns", data={"text": "回答二"}
    )

    drafted = client.post(
        f"/api/v1/capture-sessions/{session_id}/turns", data={"text": "回答三"}
    )

    assert drafted.status_code == 200
    assert drafted.json()["status"] == "needs_confirmation"
    assert drafted.json()["draft"]["things_to_note"] == "回答三"


def test_turn_requires_reflecting_state(client: TestClient) -> None:
    session_id = create_marker(client)
    response = client.post(
        f"/api/v1/capture-sessions/{session_id}/turns", data={"text": "过早回答"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE"
