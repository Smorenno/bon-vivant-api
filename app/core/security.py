from __future__ import annotations

import jwt

from app.config import settings

# Module-level JWKS client — created once on first ES256 verification, then
# reused. PyJWKClient caches public keys internally and only hits the network
# when it encounters an unknown `kid`.
_jwks_client: jwt.PyJWKClient | None = None


def _get_jwks_client() -> jwt.PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(settings.jwks_url)
    return _jwks_client


def decode_jwt(token: str) -> dict:
    """Decode and verify a Supabase JWT. All failure paths raise ValueError.

    Supports:
    - ES256  — current Supabase asymmetric keys, verified via JWKS endpoint.
    - HS256  — legacy shared-secret tokens; requires JWT_SECRET to be set.
    """
    try:
        header = jwt.get_unverified_header(token)
    except jwt.DecodeError as exc:
        raise ValueError("token_invalid") from exc

    alg: str = header.get("alg", "")

    if alg == "ES256":
        return _verify_es256(token)

    if alg == "HS256":
        return _verify_hs256(token)

    raise ValueError("unsupported token algorithm")


def _verify_es256(token: str) -> dict:
    try:
        client = _get_jwks_client()
        signing_key = client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],
            audience=settings.jwt_audience,
            leeway=settings.jwt_leeway_seconds,
        )
    except jwt.ExpiredSignatureError as exc:
        raise ValueError("token_expired") from exc
    except jwt.InvalidAudienceError as exc:
        raise ValueError("token_invalid_audience") from exc
    except jwt.InvalidSignatureError as exc:
        raise ValueError("token_invalid_signature") from exc
    except jwt.exceptions.PyJWKClientError as exc:
        # Covers key-not-found, network errors, malformed JWKS, etc.
        raise ValueError("token_invalid") from exc
    except jwt.InvalidTokenError as exc:
        raise ValueError("token_invalid") from exc


def _verify_hs256(token: str) -> dict:
    if settings.jwt_secret is None:
        raise ValueError("legacy HS256 token but no JWT secret configured")
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            audience=settings.jwt_audience,
            leeway=settings.jwt_leeway_seconds,
        )
    except jwt.ExpiredSignatureError as exc:
        raise ValueError("token_expired") from exc
    except jwt.InvalidAudienceError as exc:
        raise ValueError("token_invalid_audience") from exc
    except jwt.InvalidSignatureError as exc:
        raise ValueError("token_invalid_signature") from exc
    except jwt.InvalidTokenError as exc:
        raise ValueError("token_invalid") from exc
