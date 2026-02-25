#!/usr/bin/env python3
"""
Check why a /files/out token is invalid. Decode payload and verify signature.
Usage: python scripts/check_file_token.py "TOKEN_VALUE"
Or paste the full URL; token is taken from query param.
"""
import base64
import hmac
import hashlib
import re
import sys
from urllib.parse import parse_qs, urlparse

def main():
    raw = sys.argv[1] if len(sys.argv) > 1 else ""
    if not raw:
        print("Usage: python check_file_token.py <token_or_full_url>")
        sys.exit(1)
    # If it looks like a URL, extract token
    if "files/out" in raw or raw.startswith("http"):
        parsed = urlparse(raw)
        params = parse_qs(parsed.query)
        token_list = params.get("token") or params.get("path")  # path might be second
        if not token_list:
            print("No token= in URL")
            sys.exit(1)
        raw = token_list[0]
    token = raw.strip()
    print(f"Token length: {len(token)}")
    print(f"Token (first 50)...(last 50): {token[:50]}...{token[-50:]}")
    # Load auth_api_key from core.yml (same as result_viewer)
    key = None
    try:
        import yaml
        core_path = __file__.replace("scripts/check_file_token.py", "config/core.yml").replace("scripts\\check_file_token.py", "config\\core.yml")
        from pathlib import Path
        core_path = Path(__file__).resolve().parent.parent / "config" / "core.yml"
        with open(core_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        key_str = (cfg.get("auth_api_key") or "").strip()
        key_str = re.sub(r"[\x00-\x1f\x7f]", "", key_str) or ""
        if key_str:
            key = key_str.encode("utf-8")
        print(f"auth_api_key from config: len={len(key) if key else 0} (value hidden)")
    except Exception as e:
        print(f"Failed to load config: {e}")
        sys.exit(1)
    if not key:
        print("auth_api_key not set in config")
        sys.exit(1)
    # Token format: b64 + sig (no separator). Last 32 chars = hex sig.
    if len(token) < 33:
        print("FAIL: token too short")
        sys.exit(1)
    sig = token[-32:]
    b64 = token[:-32]
    print(f"Base64 part length: {len(b64)}")
    print(f"Signature part length: {len(sig)} (expected 32 hex chars)")
    print(f"Signature first char: {repr(sig[0])} (hex: {sig[0] in '0123456789abcdef'})")
    # Decode payload
    try:
        pad = 4 - (len(b64) % 4)
        if pad != 4:
            b64_padded = b64 + "=" * pad
        else:
            b64_padded = b64
        payload_bytes = base64.urlsafe_b64decode(b64_padded)
        payload = payload_bytes.decode("utf-8")
    except Exception as e:
        print(f"Base64 decode failed: {e}")
        # Try with 'u' appended to b64 (in case split put last b64 char in sig)
        if len(sig) == 33 and sig[0] == "u":
            b64_alt = b64 + "u"
            try:
                pad = 4 - (len(b64_alt) % 4)
                if pad != 4:
                    b64_alt += "=" * pad
                payload_bytes = base64.urlsafe_b64decode(b64_alt)
                payload = payload_bytes.decode("utf-8")
                print(f"Decode OK when appending 'u' to b64: payload={payload[:80]}...")
            except Exception as e2:
                print(f"Decode with b64+'u' also failed: {e2}")
        sys.exit(1)
    chunks = payload.split("\0", 2)
    if len(chunks) != 3:
        print(f"Payload has {len(chunks)} parts (expected 3): {chunks}")
        sys.exit(1)
    scope, path, expiry_str = chunks[0], chunks[1], chunks[2]
    print(f"Decoded payload: scope={scope!r} path={path!r} expiry_str={expiry_str!r}")
    try:
        expiry_ts = int(expiry_str)
        import time
        now = int(time.time())
        print(f"Expiry timestamp: {expiry_ts} (now={now}, expired={now > expiry_ts})")
    except ValueError:
        print("Expiry not an integer")
    # Verify signature
    expected_full = hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    expected_sig32 = expected_full[:32]
    print(f"Expected sig (32): {expected_sig32}")
    print(f"Received sig:      {sig}")
    ok32 = hmac.compare_digest(expected_sig32, sig)
    ok64 = hmac.compare_digest(expected_full, sig)
    if ok32 or ok64:
        print("Signature VERIFY OK")
    else:
        print("Signature MISMATCH")
        if len(sig) == 33 and sig[0] == "u":
            # Try: sig without first char (truncation the other way)
            sig_31 = sig[1:]
            if hmac.compare_digest(expected_sig32, sig_31):
                print("  -> If we use sig[1:] (drop first 'u'), signature matches. So the 'u' is the last char of b64 that was split into sig.")
            elif len(sig_31) == 31 and hmac.compare_digest(expected_sig32[:31], sig_31):
                print("  -> sig[1:] matches first 31 chars of expected (truncation)")
        if len(sig) == 31:
            if expected_sig32.startswith(sig):
                print("  -> Received sig is truncated (missing last char)")


if __name__ == "__main__":
    main()
