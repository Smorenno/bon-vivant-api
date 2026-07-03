from fastapi import APIRouter, Depends

from app.api.deps import get_db
from app.models.pack import PacksListResponse
from app.services import pack_service
from supabase._async.client import AsyncClient

router = APIRouter(prefix="/packs", tags=["packs"])


# Public by contract (../CLAUDE.md) and by design (migration 006 §5):
# the storefront is shown BEFORE purchase and holds no sensitive data.
@router.get("", response_model=PacksListResponse)
async def get_packs(db: AsyncClient = Depends(get_db)) -> PacksListResponse:
    return await pack_service.get_packs(db)
