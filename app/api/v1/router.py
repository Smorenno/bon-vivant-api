from fastapi import APIRouter

from app.api.v1.endpoints import cities

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(cities.router)
