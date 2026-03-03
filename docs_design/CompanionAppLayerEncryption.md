# Companion App: Application-Layer Encryption Spec

This document specifies **how the Companion app must encrypt request bodies and decrypt response bodies** when talking to HomeClaw Core with **application-layer encryption** enabled. Core implements the same scheme in `core/app_layer_encryption.py`; this spec allows a Companion (Flutter, CLI, or any client) to interoperate.

**When to use:** Only when the Core admin has set `app_layer_encryption_secret` in `config/core.yml`. The Companion must be configured with the **same secret** (e.g. from Portal, or from the same config in dev). If the secret is empty or not set, the Companion sends plain JSON and Core responds with plain JSON (no `X-Encrypted` header).

**Related:** [CompanionEncryptionAndSecurity.md](CompanionEncryptionAndSecurity.md) (overview), [SocialNetworkDesign.md](SocialNetworkDesign.md) (social network and security).

---

## 1. Algorithm and key

| Item | Value |
|------|--------|
| **Cipher** | AES-256-GCM |
| **Nonce size** | 12 bytes (96 bits) |
| **Tag size** | 16 bytes (128 bits), included in ciphertext by AES-GCM |
| **Key** | First 32 bytes of `SHA256(secret)` where `secret` is the UTF-8 encoding of the shared secret string (trimmed). |

Key derivation (pseudocode):

```
key = SHA256(secret.trim().utf8()).slice(0, 32)
```

---

## 2. Request: Companion → Core

**Endpoint:** `POST /inbound` (and optionally other endpoints that accept a JSON body and support this envelope; currently only `/inbound` is specified).

**Steps:**

1. Build the **normal request body** as JSON (e.g. `{"user_id": "...", "text": "...", "friend_id": "HomeClaw", ...}`).
2. Serialize it to UTF-8 bytes: `plaintext = JSON.stringify(body).utf8()`.
3. Generate 12 random bytes as **nonce** (cryptographically secure).
4. Encrypt: `ciphertext = AES-GCM.encrypt(key, nonce, plaintext, no_ad)` (no additional data).
5. Build the **envelope**: a JSON object with:
   - `"encrypted": true`
   - `"nonce": base64(nonce)`
   - `"ciphertext": base64(ciphertext)`
6. Send `POST /inbound` with body = that envelope (JSON), and the usual headers (e.g. `Content-Type: application/json`, `X-API-Key` or `Authorization: Bearer ...` when auth is enabled).

**Envelope format (JSON):**

```json
{
  "encrypted": true,
  "nonce": "<base64-encoded 12 bytes>",
  "ciphertext": "<base64-encoded ciphertext (encrypted plaintext + 16-byte tag)>"
}
```

Core will decrypt the body, parse the inner JSON as the real `/inbound` payload, and process it. If decryption fails, Core returns 422 or 400.

---

## 3. Response: Core → Companion

**When Core sends an encrypted response:**

- The response body is again the **same envelope format**: `{"encrypted": true, "nonce": "<b64>", "ciphertext": "<b64>"}`.
- The response **header** `X-Encrypted: true` is set.

**Steps for the Companion:**

1. Read the response body as JSON.
2. If the response **header** `X-Encrypted` is `true` (case-insensitive):
   - Parse body as the envelope; check `encrypted === true`, and that `nonce` and `ciphertext` are present.
   - Decode nonce and ciphertext from base64.
   - Decrypt: `plaintext = AES-GCM.decrypt(key, nonce, ciphertext)`.
   - Parse `plaintext` as UTF-8 JSON; that is the real response (e.g. `{"text": "...", "format": "plain"}` or `{"error": "...", "text": ""}`).
3. If `X-Encrypted` is not set or not `true`, treat the body as normal JSON (no decryption).

**Note:** Only the **sync** `POST /inbound` response (200 or 4xx/5xx JSON body) is encrypted when the request was encrypted. Async (202) and SSE (`stream: true`) responses are not wrapped in this encryption; their payloads remain plain (or can be extended later).

---

## 4. Order of operations (summary)

| Direction | Step |
|-----------|------|
| **Companion → Core (request)** | 1. Build JSON body → 2. UTF-8 encode → 3. Generate nonce → 4. AES-GCM encrypt → 5. Build envelope JSON → 6. POST body = envelope |
| **Core → Companion (response)** | 1. Read response body + headers → 2. If `X-Encrypted: true` → 3. Parse envelope → 4. Base64-decode nonce & ciphertext → 5. AES-GCM decrypt → 6. UTF-8 decode → 7. Parse JSON = actual response |

---

## 5. Libraries and platform notes

- **Dart/Flutter:** Use a package that supports AES-GCM (e.g. `pointycastle` or `cryptography`) and secure random for the nonce. Key: `sha256.convert(utf8.encode(secret.trim())).bytes.sublist(0, 32)`.
- **Python:** Use `cryptography.hazmat.primitives.ciphers.aead.AESGCM`; key = `hashlib.sha256(secret.strip().encode("utf-8")).digest()[:32]`.
- **JavaScript/TypeScript:** Use Web Crypto API `crypto.subtle` (importKey with SHA-256, then encrypt/decrypt with AES-GCM) or a library that implements AES-256-GCM with the same nonce/tag sizes.

Ensure **nonce is unique** per encryption (never reuse the same nonce with the same key). Core generates a new nonce for each encrypted response.

---

## 6. Optional: other endpoints

Currently only `POST /inbound` supports encrypted request and encrypted response. Future endpoints (e.g. `POST /api/user-message`) could use the same envelope and `X-Encrypted` header by reusing the same `parse_inbound_body` / `encrypt_response` logic on Core and the same encrypt/decrypt steps on the Companion.
