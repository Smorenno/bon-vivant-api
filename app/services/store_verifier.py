"""Server-side receipt verification against Apple and Google stores.

Low-level HTTP layer only. Raises the StoreVerificationError hierarchy;
purchase_service maps those to the public {detail, code} error schema so
no Apple/Google internals ever reach the client.

iOS  → App Store Server API (JWT auth). The deprecated verifyReceipt
       endpoint is intentionally not used.
Android → Google Play Developer API purchases.products.get, authenticated
       with a service-account OAuth2 JWT-bearer flow (no google SDK needed).
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
import jwt
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.types import PublicKeyTypes
from cryptography.hazmat.primitives.serialization import Encoding

from app.config import settings
from app.core.apple_certs import load_apple_root_ca

logger = logging.getLogger(__name__)

APPLE_PRODUCTION_URL = "https://api.storekit.itunes.apple.com"
APPLE_SANDBOX_URL = "https://api.storekit-sandbox.itunes.apple.com"
GOOGLE_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_PUBLISHER_URL = "https://androidpublisher.googleapis.com/androidpublisher/v3"
GOOGLE_PUBLISHER_SCOPE = "https://www.googleapis.com/auth/androidpublisher"

_HTTP_TIMEOUT_SECONDS = 10.0

# Store identifiers we interpolate into URL paths. Anything outside this
# alphabet is rejected before any network call (path-injection guard).
_SAFE_PATH_TOKEN = re.compile(r"^[A-Za-z0-9._-]{1,255}$")


# ============================================================
# Errors — internal only, never serialized to the client
# ============================================================


class StoreVerificationError(Exception):
    """Base class for every store verification failure."""


class StoreNotConfiguredError(StoreVerificationError):
    """Credentials missing or unusable — server-side problem."""


class StoreUnavailableError(StoreVerificationError):
    """Network failure or 5xx from Apple/Google."""


class ReceiptInvalidError(StoreVerificationError):
    """The store rejected the receipt, or its contents fail our checks
    (wrong bundle id, wrong product, refunded...). The exact reason is
    deliberately not forwarded to the client."""


@dataclass(frozen=True)
class VerifiedReceipt:
    """Normalized result of a successful store-side verification."""

    platform: str  # "ios" | "android"
    transaction_id: str
    product_id: str


def _require_safe_path_token(value: str) -> str:
    if not _SAFE_PATH_TOKEN.match(value):
        raise ReceiptInvalidError("identifier contains unexpected characters")
    return value


# ============================================================
# Apple — App Store Server API
# ============================================================


def _build_apple_api_token() -> str:
    """Build the ES256 JWT that authenticates us against the
    App Store Server API (aud=appstoreconnect-v1)."""
    if not (
        settings.apple_issuer_id
        and settings.apple_key_id
        and settings.apple_private_key
    ):
        raise StoreNotConfiguredError("Apple IAP credentials are not configured")

    now = int(time.time())
    # Env vars often carry the .p8 PEM with literal "\n" escapes.
    private_key = settings.apple_private_key.replace("\\n", "\n")
    try:
        return jwt.encode(
            {
                "iss": settings.apple_issuer_id,
                "iat": now,
                "exp": now + 300,  # Apple allows up to 60 min; keep it short
                "aud": "appstoreconnect-v1",
                "bid": settings.app_bundle_id,
            },
            private_key,
            algorithm="ES256",
            headers={"kid": settings.apple_key_id},
        )
    except (ValueError, jwt.PyJWTError) as exc:
        # Malformed/wrong-type key. Config problem, not a client problem.
        raise StoreNotConfiguredError("Apple private key is not usable") from exc


def _extract_x5c_chain(signed_info: str) -> list[x509.Certificate]:
    """Parse the x5c certificate chain from the JWS header.

    Only the (unverified) header is touched here — the payload is not
    trusted until the chain and signature checks pass.
    """
    try:
        header = jwt.get_unverified_header(signed_info)
        x5c: list[str] = header["x5c"]
        certs = [
            x509.load_der_x509_certificate(base64.b64decode(entry)) for entry in x5c
        ]
    except (KeyError, TypeError, ValueError, binascii.Error, jwt.PyJWTError) as exc:
        raise ReceiptInvalidError("malformed x5c header") from exc
    if len(certs) < 2:
        # Apple always ships leaf → WWDR intermediate (→ root). A bare
        # leaf cannot chain to anything and is rejected outright.
        raise ReceiptInvalidError("x5c chain too short")
    return certs


def _verify_x5c_chain(signed_info: str) -> PublicKeyTypes:
    """Verify the x5c chain against the pinned Apple Root CA - G3 and
    return the leaf's public key for JWS signature verification.

    Chain layout (x5c order per RFC 7515): [leaf, intermediate, ..., root?].
    Each link is checked with verify_directly_issued_by (signature +
    issuer/subject match); the anchor must BE the pinned root byte-for-byte,
    or be directly issued by it when Apple omits the root from the chain.
    """
    certs = _extract_x5c_chain(signed_info)
    pinned_root = load_apple_root_ca()

    now = datetime.now(timezone.utc)
    for cert in certs:
        if not (cert.not_valid_before_utc <= now <= cert.not_valid_after_utc):
            raise ReceiptInvalidError("certificate outside validity window")

    try:
        for child, issuer in zip(certs, certs[1:]):
            child.verify_directly_issued_by(issuer)
        anchor = certs[-1]
        if anchor.public_bytes(Encoding.DER) != pinned_root.public_bytes(Encoding.DER):
            anchor.verify_directly_issued_by(pinned_root)
    except (ValueError, TypeError, InvalidSignature) as exc:
        raise ReceiptInvalidError("x5c chain does not anchor to Apple root") from exc

    return certs[0].public_key()


def _decode_transaction_payload(signed_info: str) -> dict[str, Any]:
    """Decode Apple's signed transaction JWS.

    Two modes, switched by VERIFY_APPLE_CERT_CHAIN:
    - off (default): trust-TLS mode. The JWS was just fetched from Apple's
      host over TLS, so authenticity is anchored in that connection and the
      payload is decoded without local signature verification.
    - on: defence-in-depth. The x5c chain must anchor to the pinned
      Apple Root CA - G3 and the JWS signature must verify against the
      leaf's public key. Any failure rejects the receipt with the same
      generic error as an invalid receipt — an attacker probing this
      endpoint cannot tell the extra layer exists.
    """
    if not settings.verify_apple_cert_chain:
        # TODO(iap): flip VERIFY_APPLE_CERT_CHAIN=true after exercising the
        # chain verification against real sandbox transactions.
        try:
            return jwt.decode(signed_info, options={"verify_signature": False})
        except jwt.PyJWTError as exc:
            raise ReceiptInvalidError("unparseable transaction payload") from exc

    try:
        leaf_public_key = _verify_x5c_chain(signed_info)
        return jwt.decode(signed_info, key=leaf_public_key, algorithms=["ES256"])
    except (ReceiptInvalidError, jwt.PyJWTError) as exc:
        # The response came from Apple over TLS, so a chain/signature
        # failure here is an anomaly worth alerting on — likely tampering
        # (MITM, corporate TLS interception, or a forged response), not a
        # user error. If the payload itself still parses, that suspicion
        # hardens: someone built a well-formed transaction we cannot trust.
        payload_parses = _payload_parses_unverified(signed_info)
        logger.error(
            "apple JWS x5c verification failed (%s, payload_parses=%s) — "
            "possible tampering; transaction rejected",
            type(exc).__name__,
            payload_parses,
        )
        raise ReceiptInvalidError("x5c verification failed") from exc


def _payload_parses_unverified(signed_info: str) -> bool:
    """Best-effort classification for the tampering log — never trusted."""
    try:
        jwt.decode(signed_info, options={"verify_signature": False})
        return True
    except jwt.PyJWTError:
        return False


async def verify_ios(transaction_id: str, expected_product_id: str) -> VerifiedReceipt:
    """Verify a StoreKit 2 transaction id against the App Store Server API.

    The mobile client sends `Transaction.id` (the `receipt` field of the
    request); we fetch the signed transaction from Apple by that id, so the
    data we validate always comes from Apple, never from the client.
    """
    _require_safe_path_token(transaction_id)
    api_token = _build_apple_api_token()
    path = f"/inApps/v1/transactions/{transaction_id}"
    headers = {"Authorization": f"Bearer {api_token}"}

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.get(APPLE_PRODUCTION_URL + path, headers=headers)
            if response.status_code == 404:
                # Apple's recommended flow: transactions created in the
                # sandbox (TestFlight, App Review) 404 in production, so
                # retry against the sandbox host.
                # TODO(iap): exercise this fallback with a real sandbox
                # tester account once the Apple Developer account exists.
                response = await client.get(APPLE_SANDBOX_URL + path, headers=headers)
    except httpx.HTTPError as exc:
        logger.warning("apple store api unreachable: %s", type(exc).__name__)
        raise StoreUnavailableError("App Store Server API unreachable") from exc

    if response.status_code == 401:
        # Our JWT was rejected → bad credentials, not a bad receipt.
        raise StoreNotConfiguredError("App Store Server API rejected credentials")
    if response.status_code >= 500:
        raise StoreUnavailableError("App Store Server API error")
    if response.status_code != 200:
        # 404 in both environments, 400, etc. → unknown/invalid transaction.
        raise ReceiptInvalidError("transaction not found")

    try:
        signed_info: str = response.json()["signedTransactionInfo"]
    except (json.JSONDecodeError, KeyError) as exc:
        raise ReceiptInvalidError("unparseable transaction response") from exc

    # Trust-TLS mode by default; with VERIFY_APPLE_CERT_CHAIN=true the x5c
    # chain is verified against the pinned Apple Root CA - G3 and the JWS
    # signature against the leaf key (see _decode_transaction_payload).
    payload = _decode_transaction_payload(signed_info)

    if payload.get("bundleId") != settings.app_bundle_id:
        # Receipt from another app. Reject without detailing why.
        raise ReceiptInvalidError("bundle id mismatch")
    if payload.get("productId") != expected_product_id:
        raise ReceiptInvalidError("product id mismatch")
    if payload.get("revocationDate") is not None:
        # Refunded or revoked by Apple customer support.
        raise ReceiptInvalidError("transaction revoked")

    store_transaction_id = payload.get("transactionId")
    if not store_transaction_id:
        raise ReceiptInvalidError("transaction id missing in payload")

    return VerifiedReceipt(
        platform="ios",
        transaction_id=str(store_transaction_id),
        product_id=expected_product_id,
    )


# ============================================================
# Google — Play Developer API
# ============================================================


def _load_google_service_account() -> dict[str, Any]:
    raw = settings.google_play_service_account_json
    if not raw:
        raise StoreNotConfiguredError("Google Play service account not configured")
    try:
        if raw.lstrip().startswith("{"):
            account: dict[str, Any] = json.loads(raw)
        else:
            with open(raw, encoding="utf-8") as fh:
                account = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise StoreNotConfiguredError("Google service account JSON unusable") from exc

    if "client_email" not in account or "private_key" not in account:
        raise StoreNotConfiguredError("Google service account JSON incomplete")
    return account


async def _get_google_access_token(client: httpx.AsyncClient) -> str:
    """OAuth2 JWT-bearer flow: sign an RS256 assertion with the service
    account key and exchange it for a short-lived access token."""
    account = _load_google_service_account()
    now = int(time.time())
    try:
        assertion = jwt.encode(
            {
                "iss": account["client_email"],
                "scope": GOOGLE_PUBLISHER_SCOPE,
                "aud": GOOGLE_OAUTH_TOKEN_URL,
                "iat": now,
                "exp": now + 3600,
            },
            account["private_key"],
            algorithm="RS256",
        )
    except (ValueError, jwt.PyJWTError) as exc:
        raise StoreNotConfiguredError("Google private key is not usable") from exc

    try:
        response = await client.post(
            GOOGLE_OAUTH_TOKEN_URL,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
        )
    except httpx.HTTPError as exc:
        logger.warning("google oauth unreachable: %s", type(exc).__name__)
        raise StoreUnavailableError("Google OAuth endpoint unreachable") from exc

    if response.status_code != 200:
        # invalid_grant etc. → the service account is wrong or not linked
        # to the Play Console. Config problem.
        raise StoreNotConfiguredError("Google OAuth token exchange failed")

    try:
        return str(response.json()["access_token"])
    except (json.JSONDecodeError, KeyError) as exc:
        raise StoreUnavailableError("Google OAuth response unparseable") from exc


async def verify_android(
    purchase_token: str, expected_product_id: str
) -> VerifiedReceipt:
    """Verify a Play Billing purchase token via purchases.products.get.

    The package name in the URL is ours, so a token bought in another app
    simply does not resolve — that is the Android bundle-id check.
    """
    _require_safe_path_token(purchase_token)
    _require_safe_path_token(expected_product_id)

    url = (
        f"{GOOGLE_PUBLISHER_URL}/applications/{settings.app_bundle_id}"
        f"/purchases/products/{expected_product_id}/tokens/{purchase_token}"
    )

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
            access_token = await _get_google_access_token(client)
            headers = {"Authorization": f"Bearer {access_token}"}
            response = await client.get(url, headers=headers)

            if response.status_code in (401, 403):
                raise StoreNotConfiguredError("Play API rejected credentials")
            if response.status_code >= 500:
                raise StoreUnavailableError("Play Developer API error")
            if response.status_code != 200:
                # 400/404 → token or product unknown for our package.
                raise ReceiptInvalidError("purchase token not found")

            try:
                body: dict[str, Any] = response.json()
            except json.JSONDecodeError as exc:
                raise StoreUnavailableError("Play API response unparseable") from exc

            # purchaseState: 0 purchased · 1 canceled · 2 pending
            if body.get("purchaseState") != 0:
                raise ReceiptInvalidError("purchase not in purchased state")

            # Google refunds unacknowledged purchases after 3 days, so
            # acknowledge server-side right after validating. Best effort:
            # a failure here must not void a purchase we just verified.
            # TODO(iap): confirm acknowledgement works end-to-end with a
            # Play Console license-tester purchase once the account exists.
            if body.get("acknowledgementState") == 0:
                try:
                    ack = await client.post(f"{url}:acknowledge", headers=headers)
                    if ack.status_code != 200:
                        logger.warning(
                            "play acknowledge failed status=%s", ack.status_code
                        )
                except httpx.HTTPError as exc:
                    logger.warning("play acknowledge error: %s", type(exc).__name__)
    except httpx.HTTPError as exc:
        logger.warning("play api unreachable: %s", type(exc).__name__)
        raise StoreUnavailableError("Play Developer API unreachable") from exc

    # orderId is absent for some license-tester purchases; fall back to the
    # purchase token, which is equally unique per transaction.
    transaction_id = str(body.get("orderId") or purchase_token)

    return VerifiedReceipt(
        platform="android",
        transaction_id=transaction_id,
        product_id=expected_product_id,
    )
