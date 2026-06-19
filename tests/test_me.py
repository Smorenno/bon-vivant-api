"""Tests for GET /me and PATCH /me."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.main import app
from tests.fake_supabase import FakeSupabaseClient

USER_ID = "user-abc"
USER_EMAIL = "sergio@example.com"

_PROFILE = {
    "id": USER_ID,
    "email": USER_EMAIL,
    "full_name": "Sergio",
    "cruise_departure_date": "2025-06-15",
    "created_at": "2024-01-10T12:00:00+00:00",
    "onboarding_completed": True,
}


def _db_with_profile(profile: dict | None = None) -> FakeSupabaseClient:
    db = FakeSupabaseClient()
    db.seed("profiles", [profile or _PROFILE])
    return db


def _client(
    db: FakeSupabaseClient,
    user_id: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    async def _noop() -> None:
        pass

    monkeypatch.setattr("app.main.init_supabase", _noop)
    monkeypatch.setattr("app.main.close_supabase", _noop)
    app.dependency_overrides[deps.get_db] = lambda: db
    if user_id is not None:
        app.dependency_overrides[deps.get_current_user] = lambda: {"sub": user_id}
    else:
        app.dependency_overrides.pop(deps.get_current_user, None)
    return TestClient(app, raise_server_exceptions=False)


def _clear() -> None:
    app.dependency_overrides.clear()


# ============================================================
# GET /me
# ============================================================


def test_get_me_returns_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    with _client(_db_with_profile(), USER_ID, monkeypatch) as c:
        r = c.get("/api/v1/me")
    _clear()

    assert r.status_code == 200
    body = r.json()
    assert body["id"] == USER_ID
    assert body["email"] == USER_EMAIL
    assert body["full_name"] == "Sergio"
    assert body["onboarding_completed"] is True


def test_get_me_without_token_returns_401(monkeypatch: pytest.MonkeyPatch) -> None:
    with _client(_db_with_profile(), None, monkeypatch) as c:
        r = c.get("/api/v1/me")
    _clear()

    assert r.status_code == 401


def test_get_me_missing_profile_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeSupabaseClient()
    db.seed("profiles", [])
    with _client(db, USER_ID, monkeypatch) as c:
        r = c.get("/api/v1/me")
    _clear()

    assert r.status_code == 404
    assert r.json()["code"] == "user_not_found"


# ============================================================
# PATCH /me
# ============================================================


def test_patch_me_updates_sent_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    with _client(_db_with_profile(), USER_ID, monkeypatch) as c:
        r = c.patch("/api/v1/me", json={"full_name": "Sergio Moreno"})
    _clear()

    assert r.status_code == 200
    assert r.json()["full_name"] == "Sergio Moreno"


def test_patch_me_leaves_unsent_fields_intact(monkeypatch: pytest.MonkeyPatch) -> None:
    with _client(_db_with_profile(), USER_ID, monkeypatch) as c:
        r = c.patch("/api/v1/me", json={"cruise_departure_date": "2026-09-01"})
    _clear()

    body = r.json()
    assert r.status_code == 200
    assert body["cruise_departure_date"] == "2026-09-01"
    assert body["full_name"] == "Sergio"  # untouched


def test_patch_me_blank_name_returns_422(monkeypatch: pytest.MonkeyPatch) -> None:
    with _client(_db_with_profile(), USER_ID, monkeypatch) as c:
        r = c.patch("/api/v1/me", json={"full_name": "   "})
    _clear()

    assert r.status_code == 422


def test_patch_me_without_token_returns_401(monkeypatch: pytest.MonkeyPatch) -> None:
    with _client(_db_with_profile(), None, monkeypatch) as c:
        r = c.patch("/api/v1/me", json={"full_name": "X"})
    _clear()

    assert r.status_code == 401
