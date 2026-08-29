from fastapi.testclient import TestClient

from app.ai import FakeAIProvider
from app.models import CaptureSession
from app.schemas import ExperienceCandidate, ExperienceMatch, ReflectionAdvanceResult
from tests.conftest import advance_to_draft, create_marker


def test_fake_ai_uses_complete_conversation_and_tracks_sources(
    client: TestClient,
) -> None:
    session_id = create_marker(client)
    result = advance_to_draft(client, session_id)
    assert result["draft"]["context"] == "亲子共读活动中，三个孩子一直站在门口。"
    assert result["draft"]["observed_result"] == "孩子进来了，但现场变得比较分散。"

    detail = client.get(f"/api/v1/capture-sessions/{session_id}").json()
    assert len(detail["conversation"]) == 7
    assert [turn["kind"] for turn in detail["conversation"]] == [
        "marker",
        "question",
        "answer",
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


def test_service_rejects_a_sixth_question_and_never_creates_a_blank_draft(
    client: TestClient,
) -> None:
    client.app.state.ai_provider = AlwaysQuestionProvider()
    session_id = create_marker(client, text="一个信息不足的标记")
    client.post(f"/api/v1/capture-sessions/{session_id}/start-reflection")
    for answer in ("回答一", "回答二", "回答三", "回答四"):
        response = client.post(
            f"/api/v1/capture-sessions/{session_id}/turns", data={"text": answer}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "reflecting"

    rejected = client.post(
        f"/api/v1/capture-sessions/{session_id}/turns", data={"text": "回答五"}
    )
    assert rejected.status_code == 502
    assert rejected.json()["error"]["code"] == "AI_INVALID_OUTPUT"
    detail = client.get(f"/api/v1/capture-sessions/{session_id}").json()
    assert sum(turn["kind"] == "question" for turn in detail["conversation"]) == 5
    assert detail["draft"] is None


def test_turn_requires_reflecting_state(client: TestClient) -> None:
    session_id = create_marker(client)
    response = client.post(
        f"/api/v1/capture-sessions/{session_id}/turns", data={"text": "过早回答"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE"


def test_editing_an_answer_discards_stale_follow_up_and_regenerates(client: TestClient) -> None:
    session_id = create_marker(client)
    client.post(f"/api/v1/capture-sessions/{session_id}/start-reflection")
    client.post(f"/api/v1/capture-sessions/{session_id}/turns", data={"text": "第一次回答"})
    detail = client.get(f"/api/v1/capture-sessions/{session_id}").json()
    first_answer_id = detail["conversation"][2]["turn_id"]

    response = client.patch(
        f"/api/v1/capture-sessions/{session_id}/turns/{first_answer_id}",
        json={"text": "修正后的回答"},
    )
    assert response.status_code == 200, response.text
    detail = client.get(f"/api/v1/capture-sessions/{session_id}").json()
    assert [turn["kind"] for turn in detail["conversation"]] == [
        "marker", "question", "answer", "question"
    ]
    assert detail["conversation"][2]["text"] == "修正后的回答"
