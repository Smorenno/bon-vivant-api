from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, get_db
from app.models.city import ErrorResponse
from app.models.trip import CreateTripInput, TripResponse, TripsListResponse
from app.services import trips_service
from supabase._async.client import AsyncClient

router = APIRouter(prefix="/trips", tags=["trips"])

_ERR = {
    400: {"model": ErrorResponse},
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
}


@router.get(
    "",
    response_model=TripsListResponse,
    responses={401: {"model": ErrorResponse}},
)
async def list_trips(
    user: dict = Depends(get_current_user),
    db: AsyncClient = Depends(get_db),
) -> TripsListResponse:
    return await trips_service.get_trips(db, user["sub"])


@router.get("/{trip_id}", response_model=TripResponse, responses=_ERR)
async def get_trip(
    trip_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncClient = Depends(get_db),
) -> TripResponse:
    return await trips_service.get_trip(db, trip_id, user["sub"])


@router.post("", response_model=TripResponse, responses=_ERR, status_code=201)
async def create_trip(
    body: CreateTripInput,
    user: dict = Depends(get_current_user),
    db: AsyncClient = Depends(get_db),
) -> TripResponse:
    return await trips_service.create_trip(db, body, user["sub"])
