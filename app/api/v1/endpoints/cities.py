from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, get_db
from app.models.city import CityGuide, CityGuidePreview, CityListItem, ErrorResponse
from app.services import guide_service
from supabase import AsyncClient

router = APIRouter(prefix="/cities", tags=["cities"])

_ERROR_RESPONSES = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
}


@router.get(
    "",
    response_model=list[CityListItem],
    responses={401: {"model": ErrorResponse}},
)
async def list_cities(
    user: dict = Depends(get_current_user),
    db: AsyncClient = Depends(get_db),
) -> list[CityListItem]:
    return await guide_service.list_cities(db, user["sub"])


@router.get(
    "/{slug}",
    response_model=CityGuide,
    responses=_ERROR_RESPONSES,
)
async def get_city(
    slug: str,
    user: dict = Depends(get_current_user),
    db: AsyncClient = Depends(get_db),
) -> CityGuide:
    # CityNotFoundError → 404, CityLockedError → 403 (handled in main.py)
    return await guide_service.get_city_guide(
        db, slug, user["sub"], require_access=True
    )


@router.get(
    "/{slug}/preview",
    response_model=CityGuidePreview,
    responses=_ERROR_RESPONSES,
)
async def get_city_preview(
    slug: str,
    user: dict = Depends(get_current_user),
    db: AsyncClient = Depends(get_db),
) -> CityGuidePreview:
    return await guide_service.get_city_preview(db, slug, user["sub"])


@router.get(
    "/{slug}/offline",
    response_model=CityGuide,
    responses=_ERROR_RESPONSES,
)
async def get_city_offline_bundle(
    slug: str,
    user: dict = Depends(get_current_user),
    db: AsyncClient = Depends(get_db),
) -> CityGuide:
    """Full CityGuide bundle for offline storage (same shape as detail endpoint)."""
    return await guide_service.get_city_guide(
        db, slug, user["sub"], require_access=True
    )
