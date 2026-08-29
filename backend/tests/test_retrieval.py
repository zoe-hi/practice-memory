from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.ai import FakeAIProvider, ProviderTimeoutError
from app.models import Experience
from app.schemas import ExperienceCandidate, ExperienceMatch
from tests.conftest import create_marker


def _add_experience(
    client: TestClient,
    *,
    experience_id: str,
    activity_name: str,
    context: str,
    age: int = 0,
) -> None:
    recorded_at = datetime(2026, 8, 29, tzinfo=timezone.utc) - timedelta(minutes=age)
    with client.app.state.session_factory() as db:
        db.add(
            Experience(
                id=experience_id,
                activity_name=activity_name,
                contributor_name="脱敏贡献者",
                context=context,
                recorded_at=recorded_at,
            )
        )
        db.commit()


class RecordingProvider(FakeAIProvider):
    def __init__(self) -> None:
        super().__init__()
        self.candidate_ids: list[str] = []

    def rank_experiences(self, concern, candidates):
        del concern
        self.candidate_ids = [candidate.id for candidate in candidates]
        return None


def test_candidate_selection_prefers_normalized_exact_activity(
    client: TestClient,
) -> None:
    _add_experience(
        client,
        experience_id="exact-new",
        activity_name="亲子 共读",
        context="孩子站在门口",
    )
    _add_experience(
        client,
        experience_id="exact-old",
        activity_name=" 亲子   共读 ",
        context="孩子坐在门口",
        age=1,
    )
    _add_experience(
        client,
        experience_id="contains",
        activity_name="大型亲子 共读活动",
        context="孩子站在门口",
        age=2,
    )
    provider = RecordingProvider()
    client.app.state.ai_provider = provider

    response = client.post(
        "/api/v1/experiences/search",
        json={"activity_name": " 亲子    共读 ", "concern": "孩子在门口"},
    )
    assert response.status_code == 200
    assert provider.candidate_ids == ["exact-new", "exact-old"]


def test_unconfirmed_capture_session_is_never_a_search_candidate(
    client: TestClient,
) -> None:
    create_marker(
        client,
        text="几个孩子一直站在门口",
        activity_name="亲子共读活动",
    )
    provider = RecordingProvider()
    client.app.state.ai_provider = provider
    response = client.post(
        "/api/v1/experiences/search",
        json={"activity_name": "亲子共读活动", "concern": "孩子站在门口"},
    )
    assert response.status_code == 200
    assert response.json() == {"match": None}
    assert provider.candidate_ids == []


def test_contains_fallback_is_limited_to_twenty_recent_candidates(
    client: TestClient,
) -> None:
    for index in range(25):
        _add_experience(
            client,
            experience_id=f"candidate-{index:02d}",
            activity_name=f"第{index}场亲子共读活动",
            context="孩子站在门口",
            age=index,
        )
    provider = RecordingProvider()
    client.app.state.ai_provider = provider

    response = client.post(
        "/api/v1/experiences/search",
        json={"activity_name": "亲子共读", "concern": "孩子在门口"},
    )
    assert response.status_code == 200
    assert len(provider.candidate_ids) == 20
    assert provider.candidate_ids == [f"candidate-{index:02d}" for index in range(20)]


class OutsideCandidateProvider(FakeAIProvider):
    def rank_experiences(self, concern, candidates):
        del concern, candidates
        return ExperienceMatch(
            experience_id="not-a-candidate", why_similar="伪造的候选"
        )


class FailedRankingProvider(FakeAIProvider):
    def rank_experiences(self, concern, candidates):
        del concern, candidates
        raise ProviderTimeoutError("private provider timeout")


def test_candidate_outside_result_and_provider_failure_use_local_fallback(
    client: TestClient,
) -> None:
    _add_experience(
        client,
        experience_id="valid-candidate",
        activity_name="亲子共读活动",
        context="几个孩子一直站在门口",
    )
    for provider in (OutsideCandidateProvider(), FailedRankingProvider()):
        client.app.state.ai_provider = provider
        response = client.post(
            "/api/v1/experiences/search",
            json={"activity_name": "亲子共读活动", "concern": "孩子站在门口"},
        )
        assert response.status_code == 200
        assert response.json()["match"]["experience"]["id"] == "valid-candidate"
        assert "private provider timeout" not in response.text
        assert "not-a-candidate" not in response.text


def test_provider_none_is_a_valid_no_match_without_forced_fallback(
    client: TestClient,
) -> None:
    _add_experience(
        client,
        experience_id="would-match-locally",
        activity_name="亲子共读活动",
        context="孩子站在门口",
    )
    client.app.state.ai_provider = RecordingProvider()
    response = client.post(
        "/api/v1/experiences/search",
        json={"activity_name": "亲子共读活动", "concern": "孩子站在门口"},
    )
    assert response.status_code == 200
    assert response.json() == {"match": None}


def test_fake_ai_ties_keep_candidate_order() -> None:
    candidates = [
        ExperienceCandidate(id="newer", activity_name="活动", context="孩子站在门口"),
        ExperienceCandidate(id="older", activity_name="活动", context="孩子站在门口"),
    ]
    match = FakeAIProvider().rank_experiences("孩子站在门口", candidates)
    assert match is not None
    assert match.experience_id == "newer"
