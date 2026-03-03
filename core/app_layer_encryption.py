"""
Application-layer encryption for Companion–Core traffic.

When enabled (app_layer_encryption_secret set in core config), Core can decrypt
inbound request bodies and encrypt response bodies so content is protected
even over http. Companion must use the same secret and encrypt requests /
decrypt responses when talking to Core.

Uses AES-256-GCM: 12-byte nonce, 16-byte tag; key = SHA256(secret)[:32].
Payload format: {"encrypted": true, "nonce": "<base64>", "ciphertext": "<base64>"}.
"""

import base64
import hashlib
import json
from typing import Any, Dict, Optional, Tuple

from loguru import logger

_NONCE_SIZE = 12
_KEY_SIZE = 32
_TAG_SIZE = 16


def _derive_key(secret: str) -> bytes:
    """Derive a 32-byte key from the shared secret. Never raises; never returns empty."""
    try:
        if not secret or not isinstance(secret, str):
            return hashlib.sha256(b"homeclaw-app-layer-default").digest()
        return hashlib.sha256(secret.strip().encode("utf-8")).digest()[:_KEY_SIZE]
    except Exception:
        return hashlib.sha256(b"homeclaw-app-layer-default").digest()


def encrypt_plaintext(plaintext: bytes, secret: str) -> Optional[Dict[str, Any]]:
    """
    Encrypt plaintext with AES-256-GCM. Returns a dict suitable for JSON:
    {"encrypted": true, "nonce": "<b64>", "ciphertext": "<b64>"}.
    Returns None if encryption fails or cryptography is not available.
    """
    if not plaintext:
        return None
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        logger.debug("app_layer_encryption: cryptography not available")
        return None
    try:
        key = _derive_key(secret)
        aes = AESGCM(key)
        nonce = __import__("os").urandom(_NONCE_SIZE)
        ciphertext = aes.encrypt(nonce, plaintext, None)
        return {
            "encrypted": True,
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        }
    except Exception as e:
        logger.warning("app_layer_encryption encrypt failed: {}", e)
        return None


def decrypt_payload(body: Dict[str, Any], secret: str) -> Optional[bytes]:
    """
    If body is an encrypted payload (encrypted=true, nonce, ciphertext), decrypt
    and return plaintext bytes. Otherwise return None (caller should treat as
    unencrypted body).
    """
    if not body or not isinstance(body, dict):
        return None
    if not body.get("encrypted") or not secret or not str(secret).strip():
        return None
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        logger.debug("app_layer_encryption: cryptography not available")
        return None
    nonce_b64 = body.get("nonce")
    ct_b64 = body.get("ciphertext")
    if not nonce_b64 or not ct_b64:
        return None
    try:
        nonce = base64.b64decode(nonce_b64)
        ciphertext = base64.b64decode(ct_b64)
    except Exception:
        return None
    if len(nonce) != _NONCE_SIZE:
        return None
    try:
        key = _derive_key(secret)
        aes = AESGCM(key)
        return aes.decrypt(nonce, ciphertext, None)
    except Exception as e:
        logger.debug("app_layer_encryption decrypt failed: {}", e)
        return None


def parse_inbound_body(raw_body: bytes, secret: Optional[str]) -> Tuple[Optional[Dict[str, Any]], bool]:
    """
    Parse inbound request body. If secret is set and body looks encrypted,
    decrypt and return (decrypted_dict, True). Else parse as JSON and return
    (parsed_dict, False). On parse/decrypt error return (None, False). Never raises.
    """
    if not raw_body or not isinstance(raw_body, (bytes, bytearray)):
        return None, False
    try:
        secret = (secret or "").strip() or None
    except Exception:
        secret = None
    try:
        parsed = json.loads(raw_body.decode("utf-8"))
    except Exception:
        return None, False
    if not isinstance(parsed, dict):
        return None, False
    if secret and parsed.get("encrypted"):
        plain = decrypt_payload(parsed, secret)
        if plain is not None:
            try:
                decrypted = json.loads(plain.decode("utf-8"))
                return (decrypted, True) if isinstance(decrypted, dict) else (None, False)
            except Exception:
                return None, False
    return parsed, False


def encrypt_response(response_dict: Dict[str, Any], secret: str) -> Optional[Dict[str, Any]]:
    """
    Encrypt a response dict for the client. Returns
    {"encrypted": true, "nonce": "<b64>", "ciphertext": "<b64>"} or None if failed.
    """
    if not response_dict or not secret or not str(secret).strip():
        return None
    try:
        payload = json.dumps(response_dict, ensure_ascii=False).encode("utf-8")
        return encrypt_plaintext(payload, secret)
    except Exception as e:
        logger.debug("app_layer_encryption encrypt_response failed: {}", e)
        return None
