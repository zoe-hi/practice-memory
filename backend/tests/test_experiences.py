from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import inspect, select

from app.models import Experience
from app.seed import SEED_EXPERIENCES, seed_experiences
from tests.conftest import advance_to_draft, create_marker


def test_seed_is_idempotent_and_preserves_experience_schema(
    client: TestClient,
) -> None:
    with client.app.state.session_factory() as db:
        assert seed_experiences(db) == 6
        assert seed_experiences(db) == 0
        assert len(list(db.scalars(select(Experience)))) == 6

    columns = {
        column["name"] for column in inspect(client.app.state.engine).get_columns("experiences")
    }
    assert "capture_session_id" not in columns


def test_seed_module_command_is_idempotent(tmp_path: Path) -> None:
    database_path = tmp_path / "seed-command.db"
    environment = os.environ.copy()
    environment.update(
        {
            "DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
            "AUDIO_STORAGE_DIR": str(tmp_path / "audio"),
            "AI_PROVIDER": "fake",
        }
    )
    backend_dir = Path(__file__).resolve().parents[1]
    first = subprocess.run(
        [sys.executable, "-m", "app.seed"],
        cwd=backend_dir,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    second = subprocess.run(
        [sys.executable, "-m", "app.seed"],
        cwd=backend_dir,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Seeded 6 new experiences." in first.stdout
    assert "Seeded 0 new experiences." in second.stdout
    with sqlite3.connect(database_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM experiences").fetchone()[0]
    assert count == 6


def test_experience_list_filter_order_limit_and_public_fields(
    client: TestClient,
) -> None:
    with client.app.state.session_factory() as db:
        seed_experiences(db)

    response = client.get(
        "/api/v1/experiences",
        params={"activity_name": "  亲子共读活动  ", "limit": 2},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert [item["id"] for item in body] == [
        "00000000-0000-4000-8000-000000000503",
        "00000000-0000-4000-8000-000000000502",
    ]
    assert all(item["activity_name"] == "亲子共读活动" for item in body)
    serialized = response.text
    assert "capture_session_id" not in serialized
    assert "draft_json" not in serialized
    assert "source_turn_ids" not in serialized
    assert "audio_temp_path" not in serialized


def test_experience_detail_and_not_found_use_public_contract(
    client: TestClient,
) -> None:
    with client.app.state.session_factory() as db:
        seed_experiences(db)
    experience_id = SEED_EXPERIENCES[0]["id"]

    detail = client.get(f"/api/v1/experiences/{experience_id}")
    assert detail.status_code == 200
    assert detail.json()["id"] == experience_id
    assert detail.json()["context"].startswith("亲子共读开始后")

    missing = client.get("/api/v1/experiences/missing")
    assert missing.status_code == 404
    assert missing.json() == {
        "error": {
            "code": "EXPERIENCE_NOT_FOUND",
            "message": "经验不存在。",
            "retryable": False,
        }
    }


def test_fake_ai_search_returns_seed_match_and_no_overlap_returns_null(
    client: TestClient,
) -> None:
    with client.app.state.session_factory() as db:
        seed_experiences(db)

    matched = client.post(
        "/api/v1/experiences/search",
        json={
            "activity_name": "亲子共读活动",
            "concern": "现场很热闹，但总有孩子站在门口",
        },
    )
    assert matched.status_code == 200
    assert matched.json()["match"]["experience"]["id"] == SEED_EXPERIENCES[0]["id"]
    assert "孩子" in matched.json()["match"]["why_similar"]

    no_match = client.post(
        "/api/v1/experiences/search",
        json={"activity_name": "亲子共读活动", "concern": "量子芯片散热"},
    )
    assert no_match.status_code == 200
    assert no_match.json() == {"match": None}


def test_search_rejects_blank_input(client: TestClient) -> None:
    response = client.post(
        "/api/v1/experiences/search",
        json={"activity_name": " ", "concern": " "},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_INPUT"


def test_golden_path_confirmed_experience_can_be_read_and_found(
    client: TestClient,
) -> None:
    with client.app.state.session_factory() as db:
        seed_experiences(db)
    session_id = create_marker(client)
    advance_to_draft(client, session_id)
    patched = client.patch(
        f"/api/v1/capture-sessions/{session_id}/draft",
        json={"context": "亲子共读活动中，三个孩子一直站在门口。"},
    )
    assert patched.status_code == 200
    confirmed = client.post(
        f"/api/v1/capture-sessions/{session_id}/confirm",
        json={"contributor_name": "演示贡献者"},
    )
    assert confirmed.status_code == 201
    experience_id = confirmed.json()["id"]

    detail = client.get(f"/api/v1/experiences/{experience_id}")
    assert detail.status_code == 200
    assert detail.json()["context"] == "亲子共读活动中，三个孩子一直站在门口。"

    search = client.post(
        "/api/v1/experiences/search",
        json={"activity_name": "亲子共读活动", "concern": "总有孩子站在门口"},
    )
    assert search.status_code == 200
    assert search.json()["match"]["experience"]["id"] == experience_id
