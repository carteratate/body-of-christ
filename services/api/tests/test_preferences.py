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
