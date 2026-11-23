from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps.auth import get_current_user
from app.models.auth import AuthUser
from app.routes.preferences import router


USER_ID = "00000000-0000-0000-0000-000000000001"


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/v1")
    app.dependency_overrides[get_current_user] = lambda: AuthUser(user_id=USER_ID)
    return TestClient(app)


def _row(**overrides):
    return {
        "preferred_translation": "CPDV",
        "default_collections": ["bible"],
        "default_quota": 10,
        "last_standard_quota": 5,
        "theme": "dark",
        "result_card_style": "tint",
        **overrides,
    }


def _transactional_pool(*rows):
    conn = AsyncMock()
    conn.fetchrow.side_effect = rows
    conn.transaction = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(), __aexit__=AsyncMock(return_value=False)))
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn), __aexit__=AsyncMock(return_value=False)))
    return pool, conn


def test_get_preferences_returns_last_standard_quota():
    pool = AsyncMock()
    pool.fetchrow.return_value = _row()

    with patch("app.routes.preferences.get_pool", return_value=pool):
        response = _client().get("/v1/preferences")

    assert response.status_code == 200
    assert response.json()["last_standard_quota"] == 5
    assert "last_standard_quota" in pool.fetchrow.await_args.args[0]


def test_partial_update_validates_the_fully_merged_preference_row():
    pool, conn = _transactional_pool(_row())

    with patch("app.routes.preferences.get_pool", return_value=pool):
        response = _client().put(
            "/v1/preferences",
            json={"default_collections": ["bible", "catechism"]},
        )

    assert response.status_code == 422
    assert "exactly one collection" in response.json()["detail"]
    assert conn.fetchrow.await_count == 1


def test_update_preferences_persists_focused_and_last_standard_quotas():
    pool, conn = _transactional_pool(
        _row(default_quota=5),
        _row(),
    )

    with patch("app.routes.preferences.get_pool", return_value=pool):
        response = _client().put(
            "/v1/preferences",
            json={
                "default_collections": ["bible", "bible"],
                "default_quota": 10,
                "last_standard_quota": 5,
            },
        )

    assert response.status_code == 200
    assert response.json()["default_quota"] == 10
    upsert = conn.fetchrow.await_args_list[1]
    assert upsert.args[3] == ["bible"]
    assert upsert.args[4] == 10
    assert upsert.args[5] == 5
    assert "last_standard_quota" in upsert.args[0]
    assert "pg_advisory_xact_lock" in conn.execute.await_args.args[0]


def test_standard_and_focused_defaults_can_be_saved_and_reloaded_through_the_api():
    saved = _row(default_quota=3, last_standard_quota=3)

    async def fetchrow(query, *args):
        nonlocal saved
        if "INSERT INTO user_preferences" in query:
            saved = {
                "preferred_translation": args[1],
                "default_collections": args[2],
                "default_quota": args[3],
                "last_standard_quota": args[4],
                "theme": args[5],
                "result_card_style": args[6],
            }
        return saved

    conn = AsyncMock()
    conn.fetchrow.side_effect = fetchrow
    conn.transaction = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(), __aexit__=AsyncMock(return_value=False)))
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn), __aexit__=AsyncMock(return_value=False)))
    pool.fetchrow = AsyncMock(side_effect=fetchrow)
    client = _client()

    with patch("app.routes.preferences.get_pool", return_value=pool):
        for quota, last_standard in [(3, 3), (4, 4), (5, 5), (10, 5)]:
            response = client.put("/v1/preferences", json={
                "default_collections": ["bible"],
                "default_quota": quota,
                "last_standard_quota": last_standard,
            })
            assert response.status_code == 200
            restored = client.get("/v1/preferences")
            assert restored.status_code == 200
            assert restored.json()["default_quota"] == quota
            assert restored.json()["last_standard_quota"] == last_standard


def test_update_preferences_rejects_focused_quota_with_multiple_collections():
    pool, conn = _transactional_pool(_row(default_quota=5))

    with patch("app.routes.preferences.get_pool", return_value=pool):
        response = _client().put(
            "/v1/preferences",
            json={"default_collections": ["bible", "catechism"], "default_quota": 10},
        )

    assert response.status_code == 422
    assert conn.fetchrow.await_count == 1


def test_focused_quota_migration_adds_database_constraints():
    migration = Path(__file__).parents[3] / "supabase" / "migrations" / "0034_focused_quota_preferences.sql"
    sql = migration.read_text()

    assert "last_standard_quota" in sql
    assert "default_quota in (3, 4, 5, 10)" in sql.lower()
    assert "last_standard_quota in (3, 4, 5)" in sql.lower()
    assert "coalesce(cardinality(default_collections), 0) = 1" in sql.lower()


# ── Result card style (0046) ─────────────────────────────────────────────────

import asyncpg
import pytest

from app.routes import preferences as preferences_route


@pytest.fixture(autouse=True)
def _card_style_column_present():
    preferences_route._card_style_missing_until = 0.0
    yield
    preferences_route._card_style_missing_until = 0.0


def test_result_card_style_defaults_to_collection_tint_without_a_row():
    pool = AsyncMock()
    pool.fetchrow.return_value = None

    with patch("app.routes.preferences.get_pool", return_value=pool):
        response = _client().get("/v1/preferences")

    assert response.status_code == 200
    assert response.json()["result_card_style"] == "tint"


def test_get_preferences_returns_the_stored_result_card_style():
    pool = AsyncMock()
    pool.fetchrow.return_value = _row(result_card_style="plain")

    with patch("app.routes.preferences.get_pool", return_value=pool):
        response = _client().get("/v1/preferences")

    assert response.json()["result_card_style"] == "plain"
    assert "result_card_style" in pool.fetchrow.await_args.args[0]


def test_result_card_style_is_saved_with_the_account():
    pool, conn = _transactional_pool(
        _row(result_card_style="tint"),
        _row(result_card_style="plain"),
    )

    with patch("app.routes.preferences.get_pool", return_value=pool):
        response = _client().put("/v1/preferences", json={"result_card_style": "plain"})

    assert response.status_code == 200
    assert response.json()["result_card_style"] == "plain"
    upsert = conn.fetchrow.await_args_list[1]
    assert "result_card_style = EXCLUDED.result_card_style" in upsert.args[0]
    assert upsert.args[7] == "plain"


def test_other_updates_keep_the_stored_result_card_style():
    pool, conn = _transactional_pool(
        _row(result_card_style="plain"),
        _row(result_card_style="plain", theme="light"),
    )

    with patch("app.routes.preferences.get_pool", return_value=pool):
        response = _client().put("/v1/preferences", json={"theme": "light"})

    assert response.status_code == 200
    assert conn.fetchrow.await_args_list[1].args[7] == "plain"


def test_unknown_result_card_style_is_rejected():
    pool, conn = _transactional_pool(_row())

    with patch("app.routes.preferences.get_pool", return_value=pool):
        response = _client().put("/v1/preferences", json={"result_card_style": "striped"})

    assert response.status_code == 422
    assert conn.fetchrow.await_count == 0


def test_get_preferences_tolerates_a_database_without_the_column():
    pool = AsyncMock()
    pool.fetchrow.side_effect = [asyncpg.UndefinedColumnError("result_card_style"), _row()]

    with patch("app.routes.preferences.get_pool", return_value=pool):
        response = _client().get("/v1/preferences")
        # The answer is remembered: the next read goes straight to the old SQL.
        pool.fetchrow.side_effect = [_row()]
        again = _client().get("/v1/preferences")

    assert response.status_code == 200
    assert response.json()["result_card_style"] is None
    assert response.json()["theme"] == "dark"
    assert "result_card_style" not in pool.fetchrow.await_args.args[0]
    assert again.json()["result_card_style"] is None


def test_get_preferences_without_the_column_and_without_a_row():
    pool = AsyncMock()
    pool.fetchrow.side_effect = [asyncpg.UndefinedColumnError("result_card_style"), None]

    with patch("app.routes.preferences.get_pool", return_value=pool):
        response = _client().get("/v1/preferences")

    assert response.status_code == 200
    assert response.json()["result_card_style"] is None
    assert response.json()["default_quota"] == 4


def test_update_preferences_tolerates_a_database_without_the_column():
    pool, conn = _transactional_pool(
        asyncpg.UndefinedColumnError("result_card_style"),
        _row(),
        _row(theme="light"),
    )

    with patch("app.routes.preferences.get_pool", return_value=pool):
        response = _client().put("/v1/preferences", json={"theme": "light", "result_card_style": "plain"})

    assert response.status_code == 200
    assert response.json()["theme"] == "light"
    assert response.json()["result_card_style"] is None
    upsert = conn.fetchrow.await_args_list[2]
    assert "result_card_style" not in upsert.args[0]
    assert len(upsert.args) == 7


def test_the_column_is_tried_again_after_the_recheck_interval():
    preferences_route._card_style_missing()
    assert not preferences_route._card_style_column()
    preferences_route._card_style_missing_until -= preferences_route._RECHECK_SECONDS + 1
    assert preferences_route._card_style_column()


def test_result_card_style_migration_is_additive_with_tint_as_default():
    migration = Path(__file__).parents[3] / "supabase" / "migrations" / "0046_result_card_style_preference.sql"
    sql = migration.read_text().lower()

    assert "add column if not exists result_card_style text not null default 'tint'" in sql
    assert "result_card_style in ('tint', 'plain')" in sql
    assert "drop " not in sql and "update " not in sql


def test_card_style_alone_is_not_written_without_the_column():
    pool, conn = _transactional_pool(asyncpg.UndefinedColumnError("result_card_style"))
    pool.fetchrow = AsyncMock(return_value=_row(default_collections=["bible", "medieval-unknown"], default_quota=4))

    with patch("app.routes.preferences.get_pool", return_value=pool):
        response = _client().put("/v1/preferences", json={"result_card_style": "plain"})
        # Once the column is known missing, the same request never opens a transaction.
        second = _client().put("/v1/preferences", json={"result_card_style": "plain"})

    assert response.status_code == 200 and second.status_code == 200
    assert response.json()["result_card_style"] is None
    assert response.json()["default_collections"] == ["bible"]
    assert conn.fetchrow.await_count == 1
    assert not any("INSERT" in call.args[0] for call in conn.fetchrow.await_args_list)
    assert pool.acquire.call_count == 1


def test_an_empty_put_without_the_column_still_saves_as_before():
    pool, conn = _transactional_pool(_row(), _row())
    preferences_route._card_style_missing()

    with patch("app.routes.preferences.get_pool", return_value=pool):
        response = _client().put("/v1/preferences", json={})

    assert response.status_code == 200
    assert "INSERT INTO user_preferences" in conn.fetchrow.await_args_list[1].args[0]
