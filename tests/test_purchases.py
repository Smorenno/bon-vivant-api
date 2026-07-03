"""Tests for purchase service — GET /purchases/me, validate, restore."""

from __future__ import annotations

import uuid

import pytest

from app.exceptions import AppError
from app.models.purchase import PurchaseValidationRequest, RestoreRequest
from app.services import purchase_service, store_verifier
from app.services.store_verifier import (
    ReceiptInvalidError,
    StoreNotConfiguredError,
    VerifiedReceipt,
)
from tests.fake_supabase import FakeSupabaseClient

_USER_A = "user-a"
_USER_B = "user-b"

_PACK_ID = str(uuid.uuid4())
_CITY_ID = str(uuid.uuid4())
_PACK_ROW = {
    "id": _PACK_ID,
    "name": "Starter",
    "is_unlimited": False,
    "city_count": 3,
    "price_eur": 9.99,
    "store_product_id": "com.bonvivant.pack.starter",
}


def _make_db() -> FakeSupabaseClient:
    db = FakeSupabaseClient()
    db.seed("packs", [_PACK_ROW])
    db.seed("pack_cities", [{"pack_id": _PACK_ID, "city_id": _CITY_ID}])
    return db


def _ios_request(receipt: str = "1000000123456789") -> PurchaseValidationRequest:
    return PurchaseValidationRequest(
        receipt=receipt, platform="ios", product_id="com.bonvivant.pack.starter"
    )


def _fake_ios_verifier(monkeypatch: pytest.MonkeyPatch) -> None:
    """Store-side verification passes; transaction id derives from the receipt."""

    async def fake_verify(receipt: str, product_id: str) -> VerifiedReceipt:
        return VerifiedReceipt(
            platform="ios", transaction_id=f"txn-{receipt}", product_id=product_id
        )

    monkeypatch.setattr(store_verifier, "verify_ios", fake_verify)


# ============================================================
# 1. No purchases → empty list
# ============================================================


async def test_get_user_purchases_returns_empty_list_when_no_purchases() -> None:
    db = _make_db()
    result = await purchase_service.get_user_purchases(db, _USER_A)
    assert result.purchases == []


# ============================================================
# 2. Valid purchase → returns purchase with pack detail
# ============================================================


async def test_get_user_purchases_returns_purchase_with_pack() -> None:
    db = _make_db()
    db.seed(
        "user_purchases",
        [
            {
                "id": str(uuid.uuid4()),
                "user_id": _USER_A,
                "pack_id": _PACK_ID,
                "purchased_at": "2026-06-01T10:00:00+00:00",
                "is_valid": True,
            }
        ],
    )

    result = await purchase_service.get_user_purchases(db, _USER_A)

    assert len(result.purchases) == 1
    purchase = result.purchases[0]
    assert str(purchase.pack_id) == _PACK_ID
    assert purchase.is_valid is True
    assert purchase.pack.name == "Starter"
    assert purchase.pack.is_unlimited is False
    assert purchase.pack.city_count == 3


# ============================================================
# 3. is_valid=False purchase → not returned
# ============================================================


async def test_get_user_purchases_excludes_invalid_purchases() -> None:
    db = _make_db()
    db.seed(
        "user_purchases",
        [
            {
                "id": str(uuid.uuid4()),
                "user_id": _USER_A,
                "pack_id": _PACK_ID,
                "purchased_at": "2026-06-01T10:00:00+00:00",
                "is_valid": False,
            }
        ],
    )

    result = await purchase_service.get_user_purchases(db, _USER_A)
    assert result.purchases == []


# ============================================================
# 4. POST /purchases/validate — happy path (iOS)
# ============================================================


async def test_validate_purchase_ios_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _make_db()
    _fake_ios_verifier(monkeypatch)

    result = await purchase_service.validate_purchase(db, _USER_A, _ios_request())

    assert str(result.purchase.pack_id) == _PACK_ID
    assert result.purchase.is_valid is True
    assert [str(c) for c in result.unlocked_city_ids] == [_CITY_ID]

    rows = db.get_table("user_purchases")
    assert len(rows) == 1
    assert rows[0]["store_platform"] == "ios"
    assert rows[0]["store_transaction_id"] == "txn-1000000123456789"
    assert rows[0]["validated_at"] is not None
    assert "receipt_data" not in rows[0]  # raw receipt is never persisted


# ============================================================
# 5. validate — happy path (Android)
# ============================================================


async def test_validate_purchase_android_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _make_db()

    async def fake_verify(token: str, product_id: str) -> VerifiedReceipt:
        return VerifiedReceipt(
            platform="android", transaction_id="GPA.1234-5678", product_id=product_id
        )

    monkeypatch.setattr(store_verifier, "verify_android", fake_verify)

    request = PurchaseValidationRequest(
        receipt="play-token-abc",
        platform="android",
        product_id="com.bonvivant.pack.starter",
    )
    result = await purchase_service.validate_purchase(db, _USER_A, request)

    assert result.purchase.pack.name == "Starter"
    assert db.get_table("user_purchases")[0]["store_platform"] == "android"


# ============================================================
# 6. validate — unknown product id → 400 unknown_product
# ============================================================


async def test_validate_purchase_unknown_product() -> None:
    db = _make_db()
    request = PurchaseValidationRequest(
        receipt="r", platform="ios", product_id="com.other.app.pack"
    )

    with pytest.raises(AppError) as exc_info:
        await purchase_service.validate_purchase(db, _USER_A, request)

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "unknown_product"


# ============================================================
# 7. validate — store rejects the receipt → generic 400
# ============================================================


async def test_validate_purchase_invalid_receipt_maps_to_generic_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _make_db()

    async def fake_verify(receipt: str, product_id: str) -> VerifiedReceipt:
        raise ReceiptInvalidError("bundle id mismatch")  # internal detail

    monkeypatch.setattr(store_verifier, "verify_ios", fake_verify)

    with pytest.raises(AppError) as exc_info:
        await purchase_service.validate_purchase(db, _USER_A, _ios_request())

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "purchase_could_not_be_validated"
    # The store's internal reason must not leak into the public detail.
    assert "bundle" not in exc_info.value.detail.lower()
    assert db.get_table("user_purchases") == []


# ============================================================
# 8. validate — credentials not configured → controlled 503
# ============================================================


async def test_validate_purchase_store_not_configured_returns_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _make_db()

    async def fake_verify(receipt: str, product_id: str) -> VerifiedReceipt:
        raise StoreNotConfiguredError("Apple IAP credentials are not configured")

    monkeypatch.setattr(store_verifier, "verify_ios", fake_verify)

    with pytest.raises(AppError) as exc_info:
        await purchase_service.validate_purchase(db, _USER_A, _ios_request())

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "validation_unavailable"


async def test_verify_ios_without_credentials_raises_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real store_verifier guard: no env vars → controlled failure, no crash."""
    from app.config import settings

    monkeypatch.setattr(settings, "apple_issuer_id", None)
    monkeypatch.setattr(settings, "apple_key_id", None)
    monkeypatch.setattr(settings, "apple_private_key", None)

    with pytest.raises(StoreNotConfiguredError):
        await store_verifier.verify_ios(
            "1000000123456789", "com.bonvivant.pack.starter"
        )


async def test_verify_android_without_credentials_raises_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "google_play_service_account_json", None)

    with pytest.raises(StoreNotConfiguredError):
        await store_verifier.verify_android("token-abc", "com.bonvivant.pack.starter")


# ============================================================
# 9. validate — anti-replay via UNIQUE store_transaction_id
# ============================================================


async def test_validate_purchase_replayed_receipt_returns_409(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _make_db()
    _fake_ios_verifier(monkeypatch)

    await purchase_service.validate_purchase(db, _USER_A, _ios_request())

    with pytest.raises(AppError) as exc_info:
        await purchase_service.validate_purchase(db, _USER_A, _ios_request())

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "receipt_already_used"
    assert len(db.get_table("user_purchases")) == 1


async def test_validate_purchase_receipt_from_another_account_returns_409(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The UNIQUE index is global: a receipt redeemed by user A cannot be
    redeemed by user B (cross-account replay)."""
    db = _make_db()
    _fake_ios_verifier(monkeypatch)

    await purchase_service.validate_purchase(db, _USER_A, _ios_request())

    with pytest.raises(AppError) as exc_info:
        await purchase_service.validate_purchase(db, _USER_B, _ios_request())

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "receipt_already_used"


# ============================================================
# 10. POST /purchases/restore
# ============================================================


async def test_restore_purchases_mixed_outcomes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _make_db()
    _fake_ios_verifier(monkeypatch)

    # Receipt 1 already redeemed by this user (e.g. on a previous device).
    await purchase_service.validate_purchase(db, _USER_A, _ios_request("receipt-1"))
    # Receipt 3 already redeemed by ANOTHER user → must not be restored here.
    await purchase_service.validate_purchase(db, _USER_B, _ios_request("receipt-3"))

    request = RestoreRequest(
        purchases=[
            _ios_request("receipt-1"),  # already owned
            _ios_request("receipt-2"),  # new → restored
            _ios_request("receipt-3"),  # bound to user B → failed, silently
        ]
    )
    result = await purchase_service.restore_purchases(db, _USER_A, request)

    assert result.already_owned == 1
    assert result.restored == 1
    assert result.failed == 1
    # User A now holds exactly their two purchases.
    assert len(result.purchases) == 2


async def test_restore_purchases_empty_request_returns_current_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _make_db()
    _fake_ios_verifier(monkeypatch)
    await purchase_service.validate_purchase(db, _USER_A, _ios_request())

    result = await purchase_service.restore_purchases(db, _USER_A, RestoreRequest())

    assert result.restored == 0
    assert result.failed == 0
    assert len(result.purchases) == 1


async def test_restore_purchases_store_down_aborts_with_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _make_db()

    async def fake_verify(receipt: str, product_id: str) -> VerifiedReceipt:
        raise StoreNotConfiguredError("no credentials")

    monkeypatch.setattr(store_verifier, "verify_ios", fake_verify)

    with pytest.raises(AppError) as exc_info:
        await purchase_service.restore_purchases(
            db, _USER_A, RestoreRequest(purchases=[_ios_request()])
        )

    assert exc_info.value.status_code == 503
