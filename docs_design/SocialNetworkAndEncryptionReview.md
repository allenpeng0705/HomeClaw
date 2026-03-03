# Review: Single HomeClaw Social Network & Application-Layer Encryption

This document reviews **all code and config changes** for the single HomeClaw social network and application-layer encryption. It confirms **logic correctness** and **no-crash guarantees** for Core and Companion.

**Scope:** Application-layer encryption (Companion–Core), Friend type `user`, user-to-user message API, user inbox, test script, and documentation.

---

## 1. Summary of changes

| Area | Files | Purpose |
|------|--------|--------|
| **App-layer encryption** | `core/app_layer_encryption.py`, `core/route_registration.py`, `base/base.py`, `config/core.yml` | Optional encrypt/decrypt for `/inbound` request/response when `app_layer_encryption_secret` is set. |
| **Friend type user** | `base/base.py`, `config/user.yml` | Add `type`, `user_id` to Friend; parse/serialize in user.yml; example user-type friends. |
| **User inbox** | `core/user_inbox.py` | Append and list user-to-user messages under `data_path()/user_inbox/{user_id}.json`. |
| **User-message API** | `core/routes/user_message_api.py`, `core/routes/__init__.py`, `core/route_registration.py` | POST /api/user-message, GET /api/user-inbox; auth; deliver_to_user. |
| **Test & docs** | `scripts/test_user_message_api.py`, `README.md`, `docs_design/CompanionAppLayerEncryption.md` | Test script; README section; Companion encryption spec. |

---

## 2. Logic correctness

### 2.1 Application-layer encryption

- **Key derivation:** SHA256(secret) → first 32 bytes. Empty or invalid secret falls back to a fixed default in `_derive_key` so the function never raises; callers that require a real secret check `str(secret).strip()` before calling encrypt/decrypt.
- **Request path:** Body is read → `parse_inbound_body` returns `(dict, was_encrypted)`. If body is `{"encrypted": true, "nonce", "ciphertext"}`, Core decrypts and uses inner JSON as InboundRequest; otherwise uses body as-is. Invalid JSON or decrypt failure → `(None, False)` → 422. So: plain and encrypted clients both work; invalid payloads get 422, not 500.
- **Response path:** Only when `response_encrypted and enc_secret` and sync response, Core encrypts the JSON body and sets `X-Encrypted: true`. If `encrypt_response` returns None (e.g. crypto error), we skip encryption and return plain body so the client still gets a response.
- **Algorithms:** AES-256-GCM, 12-byte nonce, 16-byte tag; same as in Companion spec. No nonce reuse (new nonce per encrypt).

### 2.2 Friend type user

- **Parsing:** `type` and `user_id` read from user.yml; only `type == "user"` is stored; otherwise `type` is None. Backward compatible: existing friends without `type` remain AI friends.
- **Serialization:** In `_friends_to_dict_list`, we only write `type` and `user_id` when `type == "user"`. Existing YAML structure unchanged for non-user friends.
- **User list load:** `User.from_yaml` and `_parse_friends` already never raise (try/except and continue); new fields are optional and default None.

### 2.3 User inbox

- **Append:** Validates `to_user_id` and `from_user_id` non-empty; builds safe path from `user_id` (alnum + `._-` only, max 200 chars, else `_unknown`). Reads existing file, appends one message, writes back last 500 messages. On any exception returns None; caller returns 500.
- **List:** Returns up to `limit` messages (1–100); `after_id` filters to messages after that id. Non-dict entries in `messages` are skipped. On any exception returns [].

### 2.4 User-message API

- **POST /api/user-message:** Validates from_user_id and to_user_id present; resolves both users via `Util().get_users()`; checks sender has recipient as user-type friend (`type=="user"` and `user_id` match). Then appends to inbox and calls `deliver_to_user`. If inbox append fails, returns 500; if deliver_to_user throws, we catch and still return 200 with message_id (message is stored).
- **GET /api/user-inbox:** Validates user_id; coerces limit to int (default 50, clamped 1–100); returns messages. No crash path.

---

## 3. No-crash guarantees (Core)

### 3.1 core/app_layer_encryption.py

- `_derive_key`: Wrapped in try/except; on any error returns default digest. Never raises.
- `encrypt_plaintext`: Returns None on empty plaintext, ImportError, or any exception. Never raises.
- `decrypt_payload`: Returns None on invalid/missing fields, bad base64, wrong nonce length, or decrypt failure. Never raises.
- `parse_inbound_body`: Returns `(None, False)` on empty body, non-dict body, invalid UTF-8, invalid JSON, or decrypt/parse error. Checks `isinstance(raw_body, (bytes, bytearray))`. Never raises.
- `encrypt_response`: Returns None on missing/empty secret or any exception. Never raises.

### 3.2 core/route_registration.py (inbound)

- Entire parse block (body read, meta, parse_inbound_body, model_validate) is in try/except; on any exception returns 422 with message "Invalid request body". So no unhandled exception from body parsing or validation.
- Rest of handler (async_mode, stream, handle_inbound_request, response building, encryption) is inside existing try/except that returns 500 on exception. Core process does not crash.

### 3.3 core/user_inbox.py

- `_inbox_dir`: try/except; on failure returns `Path("user_inbox")`. Never raises.
- `_inbox_path`: try/except; on failure returns `_inbox_dir() / "_unknown.json"`. Never raises.
- `append_message`: Full body in try/except; on exception logs and returns None. Only adds `images`/`file_links` when `isinstance(..., (list, tuple))` to avoid non-iterable. Never raises.
- `get_messages`: Full body in try/except; on exception returns []. Iteration over messages skips non-dict items. Never raises.

### 3.4 core/routes/user_message_api.py

- `_get_user_by_id`: Uses `Util().get_users() or []`; getattr with defaults. No raise in normal use; if get_users() raises, caller (post_user_message) is inside try/except and returns 500.
- `_sender_has_recipient_as_user_friend`: getattr with defaults; only iterates friends. Never raises.
- **post_user_message:** Entire handler in try/except; on any unexpected exception returns 500 with "Internal server error". deliver_to_user is in inner try/except so its failure does not prevent 200 response.
- **get_user_inbox:** Entire handler in try/except; limit coerced with try/except to int; on any exception returns 500. Never crashes.

### 3.5 base/base.py (Friend, User)

- **Friend:** New fields `type` and `user_id` are optional (default None). No new code path that can raise.
- **_parse_friends:** Already never raises (per docstring); new logic only reads `f.get('type')`, `f.get('user_id')` and appends Friend(..., type=ftype, user_id=uid_friend). Each entry in try/except; continue on exception.
- **_friends_to_dict_list:** Already never raises; new block only adds entry["type"] and entry["user_id"] when type is "user". getattr with defaults.

---

## 4. Companion app (no crash)

- **Encryption:** Implemented per `docs_design/CompanionAppLayerEncryption.md`. Companion must:
  - Only encrypt when secret is configured; otherwise send plain JSON.
  - On response, check `X-Encrypted: true` before decrypting; if header missing, use body as plain JSON.
  - Use try/catch around decrypt so that bad ciphertext or wrong key does not crash the app; fall back to showing error or treating as plain.
- **User-message API:** Companion should validate input (from_user_id, to_user_id) before sending; handle 4xx/5xx responses without crashing. No change to Core that would cause Core to crash the client.

---

## 5. Edge cases covered

| Edge case | Handling |
|-----------|----------|
| Empty or missing request body | parse_inbound_body → (None, False) → 422. |
| Body not UTF-8 | decode throws → (None, False) → 422. |
| Body not JSON or not dict | (None, False) → 422. |
| Encrypted body but wrong secret | decrypt_payload returns None → (None, False) → 422. |
| Encrypted body, decrypt OK but inner not JSON/dict | (None, False) → 422. |
| InboundRequest.model_validate(parsed) fails (e.g. missing required field) | Exception caught → 422. |
| app_layer_encryption_secret not set | enc_secret empty; response never encrypted; plain flow. |
| Util().get_core_metadata() or data_path() fails | Caught in caller (inbound 422; inbox returns [] or None). |
| user_inbox file corrupted or not JSON | Read in try/except; append uses [] on error; get_messages returns []. |
| limit query param string or invalid | int(limit) in try/except; default 50, clamp 1–100. |
| images/file_links not list | Only list-ify when isinstance(..., (list, tuple)). |
| Message list contains non-dict | Skipped in get_messages when iterating with after_id. |

---

## 6. Files touched (checklist)

- [x] `core/app_layer_encryption.py` — encrypt/decrypt/parse; never raise; defensive _derive_key and parse_inbound_body.
- [x] `core/route_registration.py` — /inbound raw body + optional decrypt; 422 on parse error; response encryption optional.
- [x] `core/user_inbox.py` — _inbox_dir/_inbox_path safe; append_message/get_messages never raise; list/dict guards.
- [x] `core/routes/user_message_api.py` — POST/GET handlers wrapped in try/except; limit coercion; 500 on unexpected error.
- [x] `core/routes/__init__.py` — export user_message_api.
- [x] `base/base.py` — Friend type/user_id; CoreMetadata app_layer_encryption_secret; _parse_friends/_friends_to_dict_list.
- [x] `config/core.yml` — comment for app_layer_encryption_secret.
- [x] `config/user.yml` — example user-type friends (AllenPeng ↔ PengXiaoFeng).
- [x] `scripts/test_user_message_api.py` — test script (no impact on Core/Companion runtime).
- [x] `README.md` — user-message and encryption docs.
- [x] `docs_design/CompanionAppLayerEncryption.md` — Companion spec.

---

## 7. Conclusion

- **Logic:** Encryption, friend type user, inbox, and user-message API behave as designed; backward compatible; invalid inputs yield 4xx or safe fallbacks.
- **Core:** All new and modified code paths are guarded so that exceptions do not crash the process; they result in 422/500 or empty/default return values.
- **Companion:** Spec and recommendations ensure that implementing encryption and calling the user-message API can be done without crashing the app when following the doc (check header, try/catch decrypt, handle errors).

If you add new code to these areas, keep the same rules: **never let exceptions escape** (catch and return 4xx/5xx or safe default), and **validate/sanitize inputs** (type checks, length caps, safe paths).
