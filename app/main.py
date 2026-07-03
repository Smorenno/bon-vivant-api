from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.api.v1.router import api_router
from app.config import settings
from app.core.rate_limit import limiter
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


# ------------------------------------------------------------
# Security headers — defence-in-depth for any browser-reachable
# surface (/docs, error pages, future web build). Cheap and static.
# ------------------------------------------------------------
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Cache-Control", "no-store, no-cache, must-revalidate"
        )
        if not settings.debug:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
            )
        return response


app.add_middleware(SecurityHeadersMiddleware)

# ------------------------------------------------------------
# Rate limiting — global per-client default (see core/rate_limit.py).
# ------------------------------------------------------------
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

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


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(_: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests", "code": "rate_limited"},
    )


# ============================================================
# System endpoints
# ============================================================


@app.get("/health", include_in_schema=False)
async def health() -> dict:
    return {"status": "ok"}
