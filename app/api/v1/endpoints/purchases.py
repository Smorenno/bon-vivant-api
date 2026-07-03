from fastapi import APIRouter, Depends, Request

from app.api.deps import get_current_user, get_db
from app.core.rate_limit import limiter
from app.models.city import ErrorResponse
from app.models.purchase import (
    PurchasesListResponse,
    PurchaseValidationRequest,
    PurchaseValidationResponse,
    RestoreRequest,
    RestoreResponse,
)
from app.services import purchase_service
from supabase._async.client import AsyncClient

router = APIRouter(prefix="/purchases", tags=["purchases"])


@router.get(
    "/me",
    response_model=PurchasesListResponse,
    responses={401: {"model": ErrorResponse}},
)
async def get_my_purchases(
    user: dict = Depends(get_current_user),
    db: AsyncClient = Depends(get_db),
) -> PurchasesListResponse:
    return await purchase_service.get_user_purchases(db, user["sub"])


@router.post(
    "/validate",
    response_model=PurchaseValidationResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
@limiter.limit("10/minute")  # payment endpoint: tighter than the global default
async def validate_purchase(
    request: Request,
    payload: PurchaseValidationRequest,
    user: dict = Depends(get_current_user),
    db: AsyncClient = Depends(get_db),
) -> PurchaseValidationResponse:
    return await purchase_service.validate_purchase(db, user["sub"], payload)


@router.post(
    "/restore",
    response_model=RestoreResponse,
    responses={
        401: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
@limiter.limit("10/minute")
async def restore_purchases(
    request: Request,
    payload: RestoreRequest,
    user: dict = Depends(get_current_user),
    db: AsyncClient = Depends(get_db),
) -> RestoreResponse:
    return await purchase_service.restore_purchases(db, user["sub"], payload)
