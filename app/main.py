from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.config import settings
from app.db.supabase import close_supabase, init_supabase
from app.exceptions import AppError


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_supabase()
    yield
    await close_supabase()


app = FastAPI(
    title="Bon Vivant API",
    version="1.0.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
)

app.include_router(api_router)


# ============================================================
# Exception handlers — enforce {detail, code} schema everywhere
# ============================================================


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": exc.code},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": detail, "code": "http_error"},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": "Request validation failed", "code": "validation_error"},
    )


# ============================================================
# System endpoints
# ============================================================


@app.get("/health", include_in_schema=False)
async def health() -> dict:
    return {"status": "ok"}
