"""In-memory Supabase client stub for unit tests.

Implements the same fluent interface used throughout the app:
    db.table("x").select("*").eq("field", value).execute()
    db.table("x").insert({...}).execute()
    db.table("x").update({...}).eq("id", id).execute()
    db.table("x").delete().eq("id", id).execute()

Supports: select, insert (auto-UUID), update, delete, eq, in_,
maybe_single, order.  Column specs in select() are ignored (all
columns are always returned) since tests control the stored data.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

from storage3.exceptions import StorageApiError


class FakeStorageBucket:
    """In-memory stand-in for a Supabase Storage bucket handle."""

    def __init__(self, client: FakeStorageClient) -> None:
        self._client = client

    async def create_signed_url(self, path: str, _expires_in: int) -> dict[str, str]:
        if path not in self._client.existing_paths:
            raise StorageApiError(message="Object not found", code="404", status=404)
        return {"signedURL": f"https://signed.example.com/{path}"}

    async def upload(
        self, path: str, content: bytes, _file_options: dict[str, str] | None = None
    ) -> dict[str, str]:
        if path in self._client.fail_upload_paths:
            raise StorageApiError(message="Upload failed", code="500", status=500)
        self._client.uploaded[path] = content
        self._client.existing_paths.add(path)
        return {"path": path}


class FakeStorageClient:
    """In-memory stand-in for `AsyncClient.storage`.

    Tests register which storage paths "exist" via `existing_paths`; any
    other path raises StorageApiError, matching real Storage 404 behaviour.
    Paths added to `fail_upload_paths` simulate an upload failure (network,
    permissions) without affecting the rest of the batch.
    """

    def __init__(self) -> None:
        self.fail_upload_paths: set[str] = set()
        self.uploaded: dict[str, bytes] = {}
        self.existing_paths: set[str] = set()

    def from_(self, _bucket: str) -> FakeStorageBucket:
        return FakeStorageBucket(self)


class FakeQueryBuilder:
    def __init__(self, store: dict[str, list[dict]], table: str) -> None:
        self._store = store
        self._table = table
        self._op: str | None = None
        self._data: Any = None
        self._filters: dict[str, Any] = {}
        self._in_filters: dict[str, list] = {}
        self._single = False
        self._limit: int | None = None

    # ---- operation builders ------------------------------------------------

    def select(self, _cols: str = "*") -> FakeQueryBuilder:
        self._op = "select"
        return self

    def insert(self, data: dict | list) -> FakeQueryBuilder:
        self._op = "insert"
        self._data = data
        return self

    def update(self, data: dict) -> FakeQueryBuilder:
        self._op = "update"
        self._data = data
        return self

    def delete(self) -> FakeQueryBuilder:
        self._op = "delete"
        return self

    # ---- filter builders ---------------------------------------------------

    def eq(self, field: str, value: Any) -> FakeQueryBuilder:
        self._filters[field] = value
        return self

    def in_(self, field: str, values: list) -> FakeQueryBuilder:
        self._in_filters[field] = list(values)
        return self

    def maybe_single(self) -> FakeQueryBuilder:
        self._single = True
        return self

    def order(self, _col: str, **_kwargs: Any) -> FakeQueryBuilder:
        return self

    def limit(self, n: int) -> FakeQueryBuilder:
        self._limit = n
        return self

    # ---- execution ---------------------------------------------------------

    def _matches(self, row: dict) -> bool:
        for field, value in self._filters.items():
            if row.get(field) != value:
                return False
        for field, values in self._in_filters.items():
            if row.get(field) not in values:
                return False
        return True

    async def execute(self) -> SimpleNamespace:
        rows: list[dict] = self._store.setdefault(self._table, [])

        if self._op == "select":
            matched = [r for r in rows if self._matches(r)]
            if self._limit is not None:
                matched = matched[: self._limit]
            if self._single:
                return SimpleNamespace(data=matched[0] if matched else None)
            return SimpleNamespace(data=matched)

        if self._op == "insert":
            items: list[dict] = (
                self._data if isinstance(self._data, list) else [self._data]
            )
            inserted: list[dict] = []
            for item in items:
                row = {"id": str(uuid.uuid4()), **item}
                rows.append(row)
                inserted.append(row)
            return SimpleNamespace(data=inserted)

        if self._op == "update":
            updated: list[dict] = []
            for i, row in enumerate(rows):
                if self._matches(row):
                    rows[i] = {**row, **self._data}
                    updated.append(rows[i])
            return SimpleNamespace(data=updated)

        if self._op == "delete":
            deleted = [r for r in rows if self._matches(r)]
            self._store[self._table] = [r for r in rows if not self._matches(r)]
            # Propagate ON DELETE CASCADE recursively to child tables
            _cascade_delete(self._store, self._table, [r["id"] for r in deleted])
            return SimpleNamespace(data=[])

        raise RuntimeError(f"No operation set for table {self._table!r}")


# ON DELETE CASCADE rules: table → [(foreign_key_column, parent_table), ...]
# Mirrors the 002 migration's ON DELETE CASCADE constraints so that
# FakeSupabaseClient.delete() behaves like a real database.
_CASCADE: dict[str, list[tuple[str, str]]] = {
    "spots": [("city_id", "cities")],
    "itineraries": [("city_id", "cities")],
    "tips": [("city_id", "cities")],
    "images": [("city_id", "cities"), ("spot_id", "spots")],
    "pack_cities": [("city_id", "cities")],
    "itinerary_steps": [("itinerary_id", "itineraries"), ("spot_id", "spots")],
}


def _cascade_delete(
    store: dict[str, list[dict]], parent_table: str, deleted_ids: list[str]
) -> None:
    """Recursively propagate ON DELETE CASCADE for the given deleted row IDs."""
    if not deleted_ids:
        return
    for child_table, child_rules in _CASCADE.items():
        for fk_col, fk_parent in child_rules:
            if fk_parent != parent_table:
                continue
            child_rows = store.get(child_table, [])
            victims = [r for r in child_rows if r.get(fk_col) in deleted_ids]
            if not victims:
                continue
            store[child_table] = [r for r in child_rows if r not in victims]
            _cascade_delete(store, child_table, [r["id"] for r in victims])


class FakeSupabaseClient:
    """Thread-safe (within a single event loop) in-memory Supabase stub."""

    def __init__(self) -> None:
        self._store: dict[str, list[dict]] = {}
        self.storage = FakeStorageClient()

    def table(self, name: str) -> FakeQueryBuilder:
        return FakeQueryBuilder(self._store, name)

    # ---- test helpers ------------------------------------------------------

    def seed(self, table: str, rows: list[dict]) -> None:
        """Pre-populate a table for query tests."""
        self._store[table] = [dict(r) for r in rows]

    def get_table(self, name: str) -> list[dict]:
        return list(self._store.get(name, []))

    def reset(self) -> None:
        self._store.clear()
