"""Pinned Apple root certificate for App Store JWS chain verification.

The PEM lives in app/core/certs/apple_root_ca_g3.pem, downloaded from
https://www.apple.com/certificateauthority/ (Apple Root CA - G3,
SHA-256 63:34:3A:BF:B8:9A:6A:03:EB:B5:7E:9B:3F:5F:A7:BE:
        7C:4F:5C:75:6F:30:17:B3:A8:C4:88:C3:65:3E:91:79,
valid until 2039). It is a public certificate — safe to commit; what
matters is that it is pinned here and not fetched at runtime.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from cryptography import x509

_ROOT_CA_PATH = Path(__file__).parent / "certs" / "apple_root_ca_g3.pem"


@lru_cache(maxsize=1)
def load_apple_root_ca() -> x509.Certificate:
    """Load and cache the pinned Apple Root CA - G3 certificate.

    Raises FileNotFoundError / ValueError if the bundled PEM is missing or
    corrupt — both are deploy-time defects, not runtime conditions, so they
    are deliberately not converted into a store_verifier error here; the
    caller maps them to the generic invalid-receipt response.
    """
    return x509.load_pem_x509_certificate(_ROOT_CA_PATH.read_bytes())
