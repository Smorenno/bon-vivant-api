"""Tests for JWT verification (ES256 via JWKS, HS256 legacy) and admin gating.

No network calls are made: the JWKS client is replaced with a mock that returns
a key pair generated in-process using the `cryptography` library.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ec import SECP256R1, generate_private_key

import app.core.security as sec
from app.api.deps import require_admin
from app.core.security import decode_jwt
from app.exceptions import AppError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def ec_keypair():
    private_key = generate_private_key(SECP256R1())
    return private_key, private_key.public_key()


def _mock_jwks_client(public_key: object) -> MagicMock:
    signing_key = MagicMock()
    signing_key.key = public_key
    client = MagicMock()
    client.get_signing_key_from_jwt.return_value = signing_key
    return client


def _es256_token(
    private_key: object,
    *,
    aud: str = "authenticated",
    exp_delta: timedelta = timedelta(hours=1),
    extra: dict | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    claims: dict = {
        "sub": "test-user-id",
        "aud": aud,
        "iat": int(now.timestamp()),
        "exp": int((now + exp_delta).timestamp()),
    }
    if extra:
        claims.update(extra)
    return pyjwt.encode(claims, private_key, algorithm="ES256")


# ---------------------------------------------------------------------------
# ES256 via JWKS
# ---------------------------------------------------------------------------


def test_es256_valid_token_returns_claims(monkeypatch, ec_keypair):
    private_key, public_key = ec_keypair
    monkeypatch.setattr(sec, "_jwks_client", _mock_jwks_client(public_key))

    result = decode_jwt(_es256_token(private_key))

    assert result["sub"] == "test-user-id"
    assert result["aud"] == "authenticated"


def test_es256_expired_token_raises(monkeypatch, ec_keypair):
    private_key, public_key = ec_keypair
    monkeypatch.setattr(sec, "_jwks_client", _mock_jwks_client(public_key))

    token = _es256_token(private_key, exp_delta=timedelta(seconds=-60))

    with pytest.raises(ValueError, match="token_expired"):
        decode_jwt(token)


def test_es256_wrong_audience_raises(monkeypatch, ec_keypair):
    private_key, public_key = ec_keypair
    monkeypatch.setattr(sec, "_jwks_client", _mock_jwks_client(public_key))

    token = _es256_token(private_key, aud="wrong-audience")

    with pytest.raises(ValueError, match="token_invalid_audience"):
        decode_jwt(token)


def test_es256_tampered_signature_raises(monkeypatch, ec_keypair):
    private_key, _ = ec_keypair
    # Verify with a *different* public key → signature mismatch
    wrong_public_key = generate_private_key(SECP256R1()).public_key()
    monkeypatch.setattr(sec, "_jwks_client", _mock_jwks_client(wrong_public_key))

    token = _es256_token(private_key)

    with pytest.raises(ValueError):
        decode_jwt(token)


# ---------------------------------------------------------------------------
# HS256 legacy
# ---------------------------------------------------------------------------


def test_hs256_with_secret_returns_claims(monkeypatch):
    monkeypatch.setattr(sec.settings, "jwt_secret", "test-legacy-secret")

    token = pyjwt.encode(
        {
            "sub": "legacy-user",
            "aud": "authenticated",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        },
        "test-legacy-secret",
        algorithm="HS256",
    )

    result = decode_jwt(token)
    assert result["sub"] == "legacy-user"


def test_hs256_without_secret_raises(monkeypatch):
    monkeypatch.setattr(sec.settings, "jwt_secret", None)

    token = pyjwt.encode(
        {
            "sub": "legacy-user",
            "aud": "authenticated",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        },
        "some-secret",
        algorithm="HS256",
    )

    with pytest.raises(ValueError, match="no JWT secret configured"):
        decode_jwt(token)


# ---------------------------------------------------------------------------
# Unsupported algorithm
# ---------------------------------------------------------------------------


def test_unsupported_algorithm_raises():
    # Build a token with `alg: none` by hand (pyjwt refuses to sign with none,
    # so we craft the header manually)
    import base64
    import json

    def b64(data: str) -> str:
        return base64.urlsafe_b64encode(data.encode()).rstrip(b"=").decode()

    header = b64('{"alg":"RS256","typ":"JWT"}')
    payload = b64('{"sub":"x","aud":"authenticated","exp":9999999999}')
    fake_token = f"{header}.{payload}.fakesig"

    with pytest.raises(ValueError, match="unsupported token algorithm"):
        decode_jwt(fake_token)


# ---------------------------------------------------------------------------
# Admin gating
# ---------------------------------------------------------------------------


async def test_require_admin_passes_with_app_metadata_role():
    user = {"sub": "u1", "app_metadata": {"role": "admin"}}
    result = await require_admin(user)
    assert result is user


async def test_require_admin_rejects_authenticated_user():
    user = {"sub": "u2", "role": "authenticated", "app_metadata": {}}
    with pytest.raises(AppError) as exc_info:
        await require_admin(user)
    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "admin_required"
