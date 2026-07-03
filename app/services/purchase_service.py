from __future__ import annotations

import logging
from datetime import datetime, timezone

from postgrest.exceptions import APIError

from app.exceptions import AppError
from app.models.purchase import (
    PackSummary,
    PurchaseResponse,
    PurchasesListResponse,
    PurchaseValidationRequest,
    PurchaseValidationResponse,
    RestoreRequest,
    RestoreResponse,
)
from app.services import store_verifier
from app.services.store_verifier import VerifiedReceipt
from supabase._async.client import AsyncClient

logger = logging.getLogger(__name__)

# Postgres unique_violation — raised when uq_user_purchases_store_txn
# (migration 006) blocks a replayed / cross-account receipt.
_PG_UNIQUE_VIOLATION = "23505"


def _build_pack(row: dict) -> PackSummary:
    return PackSummary(
        id=row["id"],
        name=row["name"],
        is_unlimited=bool(row.get("is_unlimited", False)),
        city_count=row.get("city_count"),
    )


def _build_purchase(purchase_row: dict, pack_map: dict[str, dict]) -> PurchaseResponse:
    pack_row = pack_map[str(purchase_row["pack_id"])]
    return PurchaseResponse(
        id=purchase_row["id"],
        pack_id=purchase_row["pack_id"],
        purchased_at=purchase_row["purchased_at"],
        is_valid=bool(purchase_row.get("is_valid", True)),
        pack=_build_pack(pack_row),
    )


async def get_user_purchases(
    client: AsyncClient, user_id: str
) -> PurchasesListResponse:
    purchases_response = (
        await client.table("user_purchases")
        .select("*")
        .eq("user_id", user_id)
        .eq("is_valid", True)
        .execute()
    )
    if not purchases_response.data:
        return PurchasesListResponse(purchases=[])

    pack_ids = list({str(row["pack_id"]) for row in purchases_response.data})
    packs_response = (
        await client.table("packs").select("*").in_("id", pack_ids).execute()
    )
    pack_map = {str(row["id"]): row for row in packs_response.data}

    purchases = [_build_purchase(row, pack_map) for row in purchases_response.data]
    return PurchasesListResponse(purchases=purchases)


# ============================================================
# POST /purchases/validate
# ============================================================


async def _get_pack_by_product_id(client: AsyncClient, product_id: str) -> dict:
    response = (
        await client.table("packs")
        .select("*")
        .eq("store_product_id", product_id)
        .execute()
    )
    if not response.data:
        # product_ids are public (GET /packs), so naming the code leaks nothing
        raise AppError(400, "Unknown product", "unknown_product")
    return response.data[0]


async def _verify_with_store(request: PurchaseValidationRequest) -> VerifiedReceipt:
    """Call the right store and collapse every internal failure into the
    public error schema — Apple/Google details never reach the client."""
    try:
        if request.platform == "ios":
            return await store_verifier.verify_ios(request.receipt, request.product_id)
        return await store_verifier.verify_android(request.receipt, request.product_id)
    except store_verifier.ReceiptInvalidError as exc:
        # Real reason (bundle mismatch, refund, unknown token...) stays in
        # the server logs only, without the receipt value itself.
        logger.info("receipt rejected platform=%s reason=%s", request.platform, exc)
        raise AppError(
            400, "Purchase could not be validated", "purchase_could_not_be_validated"
        ) from exc
    except (
        store_verifier.StoreNotConfiguredError,
        store_verifier.StoreUnavailableError,
    ) as exc:
        logger.error(
            "store verification unavailable platform=%s reason=%s",
            request.platform,
            exc,
        )
        raise AppError(
            503,
            "Purchase validation is temporarily unavailable",
            "validation_unavailable",
        ) from exc


async def _record_purchase(
    client: AsyncClient, user_id: str, pack_id: str, verified: VerifiedReceipt
) -> dict:
    """Insert the validated purchase. The partial UNIQUE index on
    store_transaction_id (migration 006) is the anti-replay gate: a receipt
    already redeemed — by this or any other account — violates it."""
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "user_id": user_id,
        "pack_id": pack_id,
        "is_valid": True,
        "purchased_at": now,
        "store_platform": verified.platform,
        "store_transaction_id": verified.transaction_id,
        "validated_at": now,
        # receipt_data intentionally left NULL: the transaction id is enough
        # to re-query the store, and we avoid persisting raw client tokens.
    }
    try:
        response = await client.table("user_purchases").insert(row).execute()
    except APIError as exc:
        if exc.code == _PG_UNIQUE_VIOLATION:
            raise AppError(
                409, "This receipt has already been used", "receipt_already_used"
            ) from exc
        logger.error("user_purchases insert failed pg_code=%s", exc.code)
        raise AppError(
            503, "Purchase could not be recorded", "purchase_persist_failed"
        ) from exc
    return response.data[0]


async def _get_pack_city_ids(client: AsyncClient, pack_id: str) -> list[str]:
    response = (
        await client.table("pack_cities")
        .select("city_id")
        .eq("pack_id", pack_id)
        .execute()
    )
    return [row["city_id"] for row in response.data]


async def validate_purchase(
    client: AsyncClient, user_id: str, request: PurchaseValidationRequest
) -> PurchaseValidationResponse:
    pack_row = await _get_pack_by_product_id(client, request.product_id)
    verified = await _verify_with_store(request)
    purchase_row = await _record_purchase(client, user_id, pack_row["id"], verified)
    unlocked_city_ids = await _get_pack_city_ids(client, pack_row["id"])
    return PurchaseValidationResponse(
        purchase=_build_purchase(purchase_row, {str(pack_row["id"]): pack_row}),
        unlocked_city_ids=unlocked_city_ids,
    )


# ============================================================
# POST /purchases/restore
# ============================================================


async def _restore_one(
    client: AsyncClient, user_id: str, item: PurchaseValidationRequest
) -> str:
    """Sync a single store-reported purchase.

    Returns "restored" | "already_owned" | "failed". Per-item validation
    failures are swallowed (restore is best-effort), but a 503 — store
    down or credentials missing — aborts the whole restore upstream.
    """
    try:
        pack_row = await _get_pack_by_product_id(client, item.product_id)
        verified = await _verify_with_store(item)
    except AppError as exc:
        if exc.status_code == 503:
            raise
        return "failed"

    existing = (
        await client.table("user_purchases")
        .select("user_id")
        .eq("store_transaction_id", verified.transaction_id)
        .execute()
    )
    if existing.data:
        if any(row["user_id"] == user_id for row in existing.data):
            return "already_owned"
        # Redeemed by a different account: skip silently, leak nothing.
        logger.info("restore skipped: transaction bound to another account")
        return "failed"

    try:
        await _record_purchase(client, user_id, pack_row["id"], verified)
    except AppError as exc:
        if exc.status_code == 503:
            raise
        # Insert raced with a concurrent redemption → unique violation.
        return "failed"
    return "restored"


async def restore_purchases(
    client: AsyncClient, user_id: str, request: RestoreRequest
) -> RestoreResponse:
    counters = {"restored": 0, "already_owned": 0, "failed": 0}
    for item in request.purchases:
        counters[await _restore_one(client, user_id, item)] += 1

    current = await get_user_purchases(client, user_id)
    return RestoreResponse(
        restored=counters["restored"],
        already_owned=counters["already_owned"],
        failed=counters["failed"],
        purchases=current.purchases,
    )
