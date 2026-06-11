from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_db, require_admin
from app.models.city import CityStatus, ErrorResponse
from app.schemas.import_guide import (
    CityAdminDetail,
    CityGuideImport,
    CityUpdate,
    ImportResult,
    SpotAdminDetail,
    SpotUpdate,
)
from app.services import city_service, import_service
from app.services.exceptions import (
    CitySlugExistsError,
    GuideValidationError,
    PublishedCityReplaceError,
    SpotRefNotFoundError,
)
from app.services.geocoding_service import get_geocoder
from supabase._async.client import AsyncClient

router = APIRouter(prefix="/admin", tags=["admin"])

_ERR = {
    400: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


# ============================================================
# Import
# ============================================================


@router.post(
    "/cities/import",
    response_model=ImportResult,
    responses=_ERR,
    status_code=201,
)
async def import_city(
    guide: CityGuideImport,
    replace: bool = Query(
        False, description="Replace an existing draft if slug matches"
    ),
    _admin: dict = Depends(require_admin),
    db: AsyncClient = Depends(get_db),
) -> ImportResult:
    geocoder = get_geocoder()
    try:
        return await import_service.import_city_guide(
            guide, geocoder, db, replace=replace
        )
    except (CitySlugExistsError, PublishedCityReplaceError) as exc:
        raise exc  # already AppError with correct status code (409)
    except (SpotRefNotFoundError, GuideValidationError) as exc:
        raise exc  # already AppError with correct status code (422)


# ============================================================
# Edit city fields
# ============================================================


@router.patch(
    "/cities/{city_id}",
    response_model=CityAdminDetail,
    responses=_ERR,
)
async def patch_city(
    city_id: str,
    patch: CityUpdate,
    _admin: dict = Depends(require_admin),
    db: AsyncClient = Depends(get_db),
) -> dict:
    return await city_service.update_city(city_id, patch, db)


@router.patch(
    "/spots/{spot_id}",
    response_model=SpotAdminDetail,
    responses=_ERR,
)
async def patch_spot(
    spot_id: str,
    patch: SpotUpdate,
    _admin: dict = Depends(require_admin),
    db: AsyncClient = Depends(get_db),
) -> dict:
    return await city_service.update_spot(spot_id, patch, db)


# ============================================================
# Publish / unpublish  (consciously separate from PATCH)
# ============================================================


class _StatusResponse(CityAdminDetail):
    pass


@router.post(
    "/cities/{city_id}/publish",
    response_model=CityAdminDetail,
    responses=_ERR,
)
async def publish_city(
    city_id: str,
    _admin: dict = Depends(require_admin),
    db: AsyncClient = Depends(get_db),
) -> dict:
    return await city_service.set_city_status(city_id, CityStatus.published, db)


@router.post(
    "/cities/{city_id}/unpublish",
    response_model=CityAdminDetail,
    responses=_ERR,
)
async def unpublish_city(
    city_id: str,
    _admin: dict = Depends(require_admin),
    db: AsyncClient = Depends(get_db),
) -> dict:
    return await city_service.set_city_status(city_id, CityStatus.draft, db)
