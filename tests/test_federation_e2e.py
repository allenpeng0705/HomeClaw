"""hc-e2e-v1 envelope validation and round-trip (Python reference)."""

from __future__ import annotations

import base64

from core.federation_e2e import (
    HC_E2E_V1,
    decrypt_hc_e2e_v1,
    encrypt_hc_e2e_v1_for_test,
    envelope_to_storable_dict,
    validate_e2e_envelope,
)


def test_validate_ok() -> None:
    env = {
        "algo": HC_E2E_V1,
        "ephemeral_public_key_b64": base64.b64encode(b"\x01" * 32).decode("ascii"),
        "nonce_b64": base64.b64encode(b"\x00" * 12).decode("ascii"),
        "ciphertext_b64": base64.b64encode(b"\x00" * 16).decode("ascii"),
    }
    ok, err = validate_e2e_envelope(env)
    assert ok and err == ""


def test_validate_bad_algo() -> None:
    ok, err = validate_e2e_envelope({"algo": "x", "ephemeral_public_key_b64": "", "nonce_b64": "", "ciphertext_b64": ""})
    assert not ok and err == "unsupported_algo"


def test_validate_ciphertext_too_large() -> None:
    env = {
        "algo": HC_E2E_V1,
        "ephemeral_public_key_b64": base64.b64encode(b"\x01" * 32).decode("ascii"),
        "nonce_b64": base64.b64encode(b"\x00" * 12).decode("ascii"),
        "ciphertext_b64": base64.b64encode(b"\x00" * ((64 * 1024) + 1)).decode("ascii"),
    }
    ok, err = validate_e2e_envelope(env)
    assert not ok and err == "ciphertext_too_large"


def test_encrypt_decrypt_roundtrip() -> None:
    try:
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption, PublicFormat
    except Exception:
        return
    sk = X25519PrivateKey.generate()
    pk_raw = sk.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    priv_raw = sk.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    pt = b"hello federated e2e"
    env = encrypt_hc_e2e_v1_for_test(recipient_public_key_bytes=pk_raw, plaintext=pt)
    assert env is not None
    ok, err = validate_e2e_envelope(env)
    assert ok and err == ""
    epk = base64.b64decode(env["ephemeral_public_key_b64"], validate=True)
    nonce = base64.b64decode(env["nonce_b64"], validate=True)
    ct = base64.b64decode(env["ciphertext_b64"], validate=True)
    out = decrypt_hc_e2e_v1(
        recipient_private_key_bytes=priv_raw,
        ephemeral_public_key_bytes=epk,
        nonce=nonce,
        ciphertext=ct,
    )
    assert out == pt


def test_envelope_to_storable_dict() -> None:
    d = envelope_to_storable_dict(HC_E2E_V1, "abc", "def", "ghi")
    assert d["algo"] == HC_E2E_V1
    assert set(d.keys()) == {"algo", "ephemeral_public_key_b64", "nonce_b64", "ciphertext_b64"}
