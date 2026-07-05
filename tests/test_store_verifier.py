"""Tests for the Apple JWS x5c chain verification in store_verifier.

A throwaway CA hierarchy (root → intermediate → leaf) is generated per
test with `cryptography`, and the pinned root is monkeypatched so the
chain logic is exercised without Apple credentials or network access.
"""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import NameOID

from app.config import settings
from app.services import store_verifier
from app.services.store_verifier import ReceiptInvalidError

_PAYLOAD = {
    "bundleId": "com.bonvivant.app",
    "productId": "com.bonvivant.pack.starter",
    "transactionId": "1000000123456789",
}


def _make_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


def _make_cert(
    subject_cn: str,
    issuer_cn: str,
    public_key: ec.EllipticCurvePublicKey,
    signing_key: ec.EllipticCurvePrivateKey,
    *,
    is_ca: bool,
    not_before: datetime | None = None,
    not_after: datetime | None = None,
) -> x509.Certificate:
    now = datetime.now(timezone.utc)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject_cn)])
    issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_cn)])
    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before or now - timedelta(days=1))
        .not_valid_after(not_after or now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=is_ca, path_length=None), critical=True)
        .sign(signing_key, hashes.SHA256())
    )


class FakeAppleChain:
    """Root → intermediate → leaf hierarchy mimicking Apple's JWS chain."""

    def __init__(self) -> None:
        self.root_key = _make_key()
        self.intermediate_key = _make_key()
        self.leaf_key = _make_key()

        self.root = _make_cert(
            "Fake Apple Root",
            "Fake Apple Root",
            self.root_key.public_key(),
            self.root_key,
            is_ca=True,
        )
        self.intermediate = _make_cert(
            "Fake WWDR CA",
            "Fake Apple Root",
            self.intermediate_key.public_key(),
            self.root_key,
            is_ca=True,
        )
        self.leaf = _make_cert(
            "Fake StoreKit Signer",
            "Fake WWDR CA",
            self.leaf_key.public_key(),
            self.intermediate_key,
            is_ca=False,
        )

    def sign_jws(
        self,
        payload: dict,
        *,
        x5c_certs: list[x509.Certificate] | None = None,
        signing_key: ec.EllipticCurvePrivateKey | None = None,
    ) -> str:
        certs = x5c_certs if x5c_certs is not None else [self.leaf, self.intermediate]
        x5c = [
            base64.b64encode(cert.public_bytes(Encoding.DER)).decode() for cert in certs
        ]
        return jwt.encode(
            payload,
            signing_key or self.leaf_key,
            algorithm="ES256",
            headers={"x5c": x5c},
        )


@pytest.fixture
def chain(monkeypatch: pytest.MonkeyPatch) -> FakeAppleChain:
    """Fake hierarchy with its root pinned in place of Apple's, flag ON."""
    fake = FakeAppleChain()
    monkeypatch.setattr(store_verifier, "load_apple_root_ca", lambda: fake.root)
    monkeypatch.setattr(settings, "verify_apple_cert_chain", True)
    return fake


# ============================================================
# 1. Flag OFF (default) — trust-TLS mode is byte-for-byte unchanged
# ============================================================


def test_flag_off_decodes_without_signature_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "verify_apple_cert_chain", False)
    # JWS signed by a random key with NO x5c header: only decodable if
    # signature verification is genuinely skipped.
    signed = jwt.encode(_PAYLOAD, _make_key(), algorithm="ES256")

    payload = store_verifier._decode_transaction_payload(signed)

    assert payload["transactionId"] == "1000000123456789"


def test_flag_off_garbage_still_raises_receipt_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "verify_apple_cert_chain", False)
    with pytest.raises(ReceiptInvalidError):
        store_verifier._decode_transaction_payload("not-a-jws")


# ============================================================
# 2. Flag ON — happy paths
# ============================================================


def test_valid_chain_and_signature_decodes(chain: FakeAppleChain) -> None:
    signed = chain.sign_jws(_PAYLOAD)  # [leaf, intermediate], root pinned
    payload = store_verifier._decode_transaction_payload(signed)
    assert payload["bundleId"] == "com.bonvivant.app"


def test_valid_chain_with_root_included_decodes(chain: FakeAppleChain) -> None:
    # Apple sometimes ships the full chain including the root: the anchor
    # then matches the pinned root byte-for-byte.
    signed = chain.sign_jws(
        _PAYLOAD, x5c_certs=[chain.leaf, chain.intermediate, chain.root]
    )
    payload = store_verifier._decode_transaction_payload(signed)
    assert payload["transactionId"] == "1000000123456789"


# ============================================================
# 3. Flag ON — rejections (all collapse to ReceiptInvalidError)
# ============================================================


def test_signature_by_wrong_key_rejected(chain: FakeAppleChain) -> None:
    # Valid chain in the header, but the JWS is signed by an attacker key.
    signed = chain.sign_jws(_PAYLOAD, signing_key=_make_key())
    with pytest.raises(ReceiptInvalidError):
        store_verifier._decode_transaction_payload(signed)


def test_chain_anchored_to_foreign_root_rejected(chain: FakeAppleChain) -> None:
    # A fully self-consistent chain... anchored to someone else's root.
    foreign = FakeAppleChain()
    signed = foreign.sign_jws(
        _PAYLOAD,
        x5c_certs=[foreign.leaf, foreign.intermediate, foreign.root],
        signing_key=foreign.leaf_key,
    )
    with pytest.raises(ReceiptInvalidError):
        store_verifier._decode_transaction_payload(signed)


def test_missing_x5c_header_rejected(chain: FakeAppleChain) -> None:
    signed = jwt.encode(_PAYLOAD, chain.leaf_key, algorithm="ES256")  # no x5c
    with pytest.raises(ReceiptInvalidError):
        store_verifier._decode_transaction_payload(signed)


def test_single_cert_chain_rejected(chain: FakeAppleChain) -> None:
    signed = chain.sign_jws(_PAYLOAD, x5c_certs=[chain.leaf])
    with pytest.raises(ReceiptInvalidError):
        store_verifier._decode_transaction_payload(signed)


def test_expired_leaf_rejected(chain: FakeAppleChain) -> None:
    now = datetime.now(timezone.utc)
    expired_leaf = _make_cert(
        "Fake StoreKit Signer",
        "Fake WWDR CA",
        chain.leaf_key.public_key(),
        chain.intermediate_key,
        is_ca=False,
        not_before=now - timedelta(days=30),
        not_after=now - timedelta(days=1),
    )
    signed = chain.sign_jws(_PAYLOAD, x5c_certs=[expired_leaf, chain.intermediate])
    with pytest.raises(ReceiptInvalidError):
        store_verifier._decode_transaction_payload(signed)


def test_chain_failure_logs_tampering_alert(
    chain: FakeAppleChain, caplog: pytest.LogCaptureFixture
) -> None:
    """A parseable payload failing chain verification must leave an ERROR
    trace (attack indicator) without leaking receipt contents."""
    signed = chain.sign_jws(_PAYLOAD, signing_key=_make_key())

    with caplog.at_level("ERROR", logger="app.services.store_verifier"):
        with pytest.raises(ReceiptInvalidError):
            store_verifier._decode_transaction_payload(signed)

    assert any("payload_parses=True" in r.message for r in caplog.records)
    # No receipt/payload material in the log line.
    assert all("1000000123456789" not in r.message for r in caplog.records)


# ============================================================
# 4. Bundled pinned root sanity
# ============================================================


def test_bundled_apple_root_ca_is_the_g3_self_signed_root() -> None:
    from app.core.apple_certs import load_apple_root_ca

    root = load_apple_root_ca()
    cn = root.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
    assert cn == "Apple Root CA - G3"
    assert root.subject == root.issuer  # self-signed
    root.verify_directly_issued_by(root)  # signature actually verifies
