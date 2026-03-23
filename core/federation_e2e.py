"""
Federated user-message E2E envelope (hc-e2e-v1): X25519 ephemeral + AES-256-GCM.

Core does not decrypt; only validates structure and sizes. See docs_design/FederatedCompanionUserMessaging.md P5.
"""

from __future__ import annotations

import base64
from typing import Any, Dict, Optional, Tuple

HC_E2E_V1 = "hc-e2e-v1"


def validate_e2e_envelope(raw: Any) -> Tuple[bool, str]:
    """Return (ok, error_code). Never raises."""
    if not isinstance(raw, dict):
        return False, "invalid_envelope"
    algo = (raw.get("algo") or "").strip()
    if algo != HC_E2E_V1:
        return False, "unsupported_algo"
    try:
        epk = base64.b64decode((raw.get("ephemeral_public_key_b64") or raw.get("ephemeral_public_key") or "").strip(), validate=True)
        if len(epk) != 32:
            return False, "bad_ephemeral_key_length"
    except Exception:
        return False, "bad_ephemeral_key_b64"
    try:
        nonce = base64.b64decode((raw.get("nonce_b64") or raw.get("nonce") or "").strip(), validate=True)
        if len(nonce) != 12:
            return False, "bad_nonce_length"
    except Exception:
        return False, "bad_nonce_b64"
    try:
        ct = base64.b64decode((raw.get("ciphertext_b64") or raw.get("ciphertext") or "").strip(), validate=True)
        if len(ct) < 16:
            return False, "ciphertext_too_short"
    except Exception:
        return False, "bad_ciphertext_b64"
    return True, ""


def envelope_to_storable_dict(
    algo: str,
    ephemeral_public_key_b64: str,
    nonce_b64: str,
    ciphertext_b64: str,
) -> Dict[str, str]:
    return {
        "algo": (algo or "").strip() or HC_E2E_V1,
        "ephemeral_public_key_b64": (ephemeral_public_key_b64 or "").strip(),
        "nonce_b64": (nonce_b64 or "").strip(),
        "ciphertext_b64": (ciphertext_b64 or "").strip(),
    }


def decrypt_hc_e2e_v1(
    *,
    recipient_private_key_bytes: bytes,
    ephemeral_public_key_bytes: bytes,
    nonce: bytes,
    ciphertext: bytes,
) -> Optional[bytes]:
    """
    Decrypt for tests / tooling only (Companion does crypto on device). Returns plaintext bytes or None.
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    except Exception:
        return None
    try:
        if len(recipient_private_key_bytes) != 32 or len(ephemeral_public_key_bytes) != 32:
            return None
        sk = X25519PrivateKey.from_private_bytes(recipient_private_key_bytes)
        peer_pub = X25519PublicKey.from_public_bytes(ephemeral_public_key_bytes)
        shared = sk.exchange(peer_pub)
        hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"homeclaw-fed-e2e-v1", info=b"")
        aes_key = hkdf.derive(shared)
        aesgcm = AESGCM(aes_key)
        return aesgcm.decrypt(nonce, ciphertext, None)
    except Exception:
        return None


def encrypt_hc_e2e_v1_for_test(
    *,
    recipient_public_key_bytes: bytes,
    plaintext: bytes,
) -> Optional[Dict[str, str]]:
    """Generate envelope (for tests). Returns dict with b64 fields."""
    try:
        import os

        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    except Exception:
        return None
    try:
        if len(recipient_public_key_bytes) != 32:
            return None
        epriv = X25519PrivateKey.generate()
        epub = epriv.public_key()
        peer_pub = X25519PublicKey.from_public_bytes(recipient_public_key_bytes)
        shared = epriv.exchange(peer_pub)
        hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"homeclaw-fed-e2e-v1", info=b"")
        aes_key = hkdf.derive(shared)
        nonce = os.urandom(12)
        aesgcm = AESGCM(aes_key)
        ct = aesgcm.encrypt(nonce, plaintext, None)
        epk_raw = epub.public_bytes(Encoding.Raw, PublicFormat.Raw)
        return {
            "algo": HC_E2E_V1,
            "ephemeral_public_key_b64": base64.b64encode(epk_raw).decode("ascii"),
            "nonce_b64": base64.b64encode(nonce).decode("ascii"),
            "ciphertext_b64": base64.b64encode(ct).decode("ascii"),
        }
    except Exception:
        return None
