from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select

from app.models import CaptureSession, Experience
from tests.conftest import advance_to_draft, create_marker


def test_cannot_confirm_before_draft(client: TestClient) -> None:
    session_id = create_marker(client)
    response = client.post(
        f"/api/v1/capture-sessions/{session_id}/confirm",
        json={"contributor_name": "演示贡献者"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE"


def test_invalid_draft_extra_field_uses_contract_error(client: TestClient) -> None:
    session_id = create_marker(client)
    advance_to_draft(client, session_id)
    response = client.patch(
        f"/api/v1/capture-sessions/{session_id}/draft",
        json={"context": "确认事实", "invented_field": "不允许"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_DRAFT"


def test_manual_draft_edit_is_saved_and_confirmation_is_idempotent(
    client: TestClient,
) -> None:
    session_id = create_marker(client)
    advance_to_draft(client, session_id)
    edited = client.patch(
        f"/api/v1/capture-sessions/{session_id}/draft",
        json={
            "context": "贡献者确认后的现场事实。",
            "open_question": None,
        },
    )
    assert edited.status_code == 200
    assert edited.json()["draft"]["context"] == "贡献者确认后的现场事实。"

    payload = {"contributor_name": "演示贡献者", "contributor_role": "活动带领者"}
    first = client.post(
        f"/api/v1/capture-sessions/{session_id}/confirm", json=payload
    )
    second = client.post(
        f"/api/v1/capture-sessions/{session_id}/confirm", json=payload
    )
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["context"] == "贡献者确认后的现场事实。"
    assert "source_turn_ids" not in first.json()

    factory = client.app.state.session_factory
    with factory() as db:
        count = db.scalar(select(func.count()).select_from(Experience))
        session = db.get(CaptureSession, session_id)
        assert count == 1
        assert session.status == "confirmed"
        assert session.confirmed_experience_id == first.json()["id"]
        assert session.draft_json["source_turn_ids"]["context"] == ["manual_edit"]


def test_experience_table_has_no_capture_session_id(client: TestClient) -> None:
    columns = {
        column["name"]
        for column in inspect(client.app.state.engine).get_columns("experiences")
    }
    assert "capture_session_id" not in columns


def test_concurrent_confirmation_creates_only_one_experience(
    client: TestClient,
) -> None:
    session_id = create_marker(client)
    advance_to_draft(client, session_id)
    url = f"/api/v1/capture-sessions/{session_id}/confirm"
    payload = {"contributor_name": "并发测试贡献者"}

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(lambda _: client.post(url, json=payload), range(2))
        )

    assert sorted(response.status_code for response in responses) == [200, 201]
    assert len({response.json()["id"] for response in responses}) == 1
    factory = client.app.state.session_factory
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Experience)) == 1


def test_phase_two_golden_path(client: TestClient) -> None:
    session_id = create_marker(client)
    advance_to_draft(client, session_id)
    edited = client.patch(
        f"/api/v1/capture-sessions/{session_id}/draft",
        json={"things_to_note": "下次提前准备活动重新收拢的方法。"},
    )
    assert edited.status_code == 200
    confirmed = client.post(
        f"/api/v1/capture-sessions/{session_id}/confirm",
        json={"contributor_name": "吴瑶儿", "contributor_role": "乡村图书馆员"},
    )
    assert confirmed.status_code == 201
    assert confirmed.json()["things_to_note"] == "下次提前准备活动重新收拢的方法。"
