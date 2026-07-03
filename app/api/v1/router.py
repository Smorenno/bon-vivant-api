from fastapi import APIRouter

from app.api.v1.endpoints import admin_cities, cities, me, packs, purchases, trips

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(me.router)
api_router.include_router(cities.router)
api_router.include_router(admin_cities.router)
api_router.include_router(packs.router)
api_router.include_router(purchases.router)
api_router.include_router(trips.router)
