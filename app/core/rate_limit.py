from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


# Behind Railway's proxy the socket peer is the proxy, so request.client.host
# would collapse every user onto one bucket. Railway sets X-Forwarded-For with
# the real client as the first hop; fall back to the socket address locally.
def client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


# In-memory storage: per-process, resets on restart. Good enough as a first
# line of defence; back it with Redis (storage_uri="redis://…") when the API
# scales to multiple Railway instances and limits must be shared.
limiter = Limiter(
    key_func=client_key,
    default_limits=["120/minute"],
    headers_enabled=True,
)
