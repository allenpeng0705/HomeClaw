# Encrypted storage for auth_api_key (design)

This document explains how HomeClaw can store the Core API key (`auth_api_key`) **encrypted at rest** in `config/core.yml`, and how load/save and backward compatibility work.

---

## 1. Purpose

- **auth_api_key** in `config/core.yml` is the secret that clients (Companion, channels, scripts) send as `X-API-Key` or `Authorization: Bearer <key>` when `auth_enabled` is true.
- Storing it in **plain text** is simple but exposes the key to anyone with read access to the config file (e.g. shared disks, backups, version control mistakes).
- **Encrypted storage** keeps the value on disk as `encrypted:<base64>` so that without the decryption key (from the environment), the file does not reveal the actual API key.

---

## 2. Module: `base/auth_api_key_crypto.py`

This module provides two main functions and never raises; it always returns a string or falls back to a safe default.

### 2.1 Environment key

- **Variable:** `HOMECLAW_AUTH_KEY`
- **Role:** A secret string (passphrase or random bytes) used **only** to derive the encryption/decryption key. It is **not** the API key itself.
- **When set:** Core and Portal will **encrypt** the API key when writing config and **decrypt** it when reading. When **not** set, the module behaves as a no-op for encryption and leaves plain values unchanged.

### 2.2 Key derivation (Fernet key)

Fernet (from the `cryptography` library) expects a key that is:

- 32 bytes of raw key material, then
- Base64url-encoded into a single string.

We derive that key from the environment:

1. Read `HOMECLAW_AUTH_KEY` from the environment and strip whitespace.
2. UTF-8 encode the string and compute **SHA-256**: `digest = SHA256(env_value)` → 32 bytes.
3. **Base64url-encode** the digest: `key = base64.urlsafe_b64encode(digest)` → this is the Fernet key.

So: **same env value → same Fernet key every time** (no salt). The env value must be kept secret; anyone with it can decrypt any `auth_api_key` that was encrypted with it.

### 2.3 `decrypt_auth_api_key(value)`

**Behavior:**

- **Input:** The raw string from config (e.g. from YAML), possibly `None` or empty.
- **Output:** The plain API key string to use in memory.

**Logic:**

1. If `value` is missing or not a string, return a normalized empty/cleaned string.
2. Strip `value`. If it does **not** start with the prefix `"encrypted:"`, treat it as **plain text** and return it as-is (backward compatibility).
3. If it **does** start with `"encrypted:"`:
   - Take the rest of the string (the base64-encoded Fernet token).
   - Lazy-import `cryptography.fernet.Fernet`; if import fails, return `""`.
   - Get the Fernet key from `_get_fernet_key()`; if the env is not set, return `""`.
   - Build `Fernet(key)`, decrypt the token, decode the result to UTF-8 and return it.
   - On any exception (bad token, wrong key, etc.), return `""`.

So: **only** values that start with `"encrypted:"` are decrypted; everything else is returned unchanged. Decryption failures result in an empty string so Core does not crash and simply sees “no key”.

### 2.4 `encrypt_auth_api_key(plain)`

**Behavior:**

- **Input:** The plain API key string (e.g. from in-memory config or from a user/API).
- **Output:** Either the same string (plain) or `"encrypted:" + base64_token`.

**Logic:**

1. If `plain` is missing, not a string, or empty after strip, return a normalized empty or plain value.
2. Lazy-import `Fernet`; if import fails, return `plain` unchanged.
3. Get the Fernet key from `_get_fernet_key()`; if the env is not set, return `plain` unchanged.
4. Build `Fernet(key)`, encrypt `plain.encode("utf-8")`, then format as `"encrypted:" + token.decode("ascii")` and return that.
5. On any exception, return `plain` unchanged.

So: **encryption is best-effort**. If the env is set and `cryptography` works, we write encrypted; otherwise we write plain and never raise.

### 2.5 `is_encryption_available()`

Returns `True` only if:

- `HOMECLAW_AUTH_KEY` is set and non-empty, and  
- `cryptography.fernet.Fernet` can be imported.

Used to report whether encrypted storage is possible (e.g. for docs or diagnostics).

### 2.6 Failure and compatibility

- **No `cryptography`:** Encrypt returns plain; decrypt of `"encrypted:..."` returns `""`.
- **No `HOMECLAW_AUTH_KEY`:** Encrypt returns plain; decrypt of `"encrypted:..."` returns `""`.
- **Wrong or changed env key:** Decrypt of an old `"encrypted:..."` value fails and returns `""` (effective “no key” until config is fixed).
- **Plain value in config:** Always returned as-is by decrypt; encrypt may still output plain if env or crypto is unavailable.

So: **backward compatible**. Existing configs with plain `auth_api_key` keep working; encryption is optional and best-effort.

---

## 3. Load path: when Core (or Portal) reads config

**Where:** `base/base.py`, `CoreMetadata.from_yaml()` (and any code that builds metadata from the same YAML data).

**Flow:**

1. Config is loaded from disk (e.g. `config/core.yml`), possibly merged with other files.
2. The raw value for `auth_api_key` is read from the parsed dict (e.g. `data.get('auth_api_key')`). It may be:
   - A plain string: `"my-secret-key"`,
   - An encrypted string: `"encrypted:gAAAAABh..."`,
   - Or missing/empty.
3. Before building `CoreMetadata`, the value is passed through **`decrypt_auth_api_key(...)`**:
   - Plain → returned as-is.
   - `"encrypted:..."` → decrypted with Fernet (if env and crypto are available); on failure, `""`.
4. The result is assigned to `CoreMetadata.auth_api_key` and used everywhere (auth checks, file-link signing, etc.).

**Important:** In-memory, **`auth_api_key` is always the plain key**. No component ever stores or compares an encrypted value at runtime; encryption only affects what is written to or read from the config file.

---

## 4. Save paths: when config is written to disk

There are three places that can write `auth_api_key` into `config/core.yml`. In each case, the **value that gets written** is passed through **`encrypt_auth_api_key(...)`** so that, when the env is set and crypto is available, the file receives `"encrypted:..."` instead of plain text.

### 4.1 `CoreMetadata.to_yaml(core, yaml_file)` (base/base.py)

- Used when Core (or a script) serializes the in-memory `CoreMetadata` back to YAML (e.g. after loading and merging, or when saving state).
- When building the dict that will be written, the key `'auth_api_key'` is set to:
  - `encrypt_auth_api_key(getattr(core, 'auth_api_key', '') or '') or ''`
- So: the **in-memory** (plain) `core.auth_api_key` is encrypted for the serialized dict; if encryption is unavailable or returns empty, the existing logic may still write an empty or plain value depending on the rest of `to_yaml` (e.g. merge with existing file). The design intent is: whenever we write, we prefer encrypted form when possible.

### 4.2 Core API: `PATCH /api/config/core` (core/routes/config_api.py)

- The client sends a JSON body that may include `auth_api_key` (e.g. a new or updated key from the Companion “Config Core” screen or an admin tool).
- The handler merges the body into the in-memory config dict that will be written to `core.yml`.
- **Before** calling `Util().update_yaml_preserving_comments(path, data)`:
  - If `data["auth_api_key"]` is present, is a non-empty string, and does **not** already start with `"encrypted:"`, it is replaced with:
    - `encrypt_auth_api_key(data["auth_api_key"]) or data["auth_api_key"]`
- So: when the client sends a **plain** key and the env is set, the file gets the **encrypted** form. If the client ever sent `"encrypted:..."` (e.g. from a previous read that was redacted as `***` and not re-sent), we do not double-encrypt because of the `startswith("encrypted:")` check (and in practice the API redacts the key on GET, so the client usually sends either a new plain key or omits it).

### 4.3 Portal: `update_config("core", body)` (portal/config_api.py)

- When the Portal updates Core config (e.g. from its own UI), it merges `body` into the core config and then calls `yaml_config.update_yml_preserving(path, core_body, ...)`.
- **Before** that call:
  - If `core_body["auth_api_key"]` is present, is a non-empty string, and does **not** start with `"encrypted:"`, it is replaced with:
    - `encrypt_auth_api_key(core_body["auth_api_key"]) or core_body["auth_api_key"]`
- So: same as the Core PATCH path — plain keys from the Portal are written encrypted when the env is set.

**Summary of save behavior:** Whenever Core or Portal writes `auth_api_key` to `core.yml`, it uses `encrypt_auth_api_key(plain)`. If `HOMECLAW_AUTH_KEY` is set and `cryptography` is available, the value on disk becomes `"encrypted:<base64>"`; otherwise it stays plain. The in-memory value remains plain in all cases.

---

## 5. Backward compatibility and safe fallbacks

- **Existing installs:** Config files that already have plain `auth_api_key` are unchanged. `decrypt_auth_api_key` returns them as-is. No migration step is required.
- **New installs or enabling encryption later:** Set `HOMECLAW_AUTH_KEY`, install `cryptography`, then set or change the API key once via Portal or PATCH; the next save will write `"encrypted:..."`.
- **Env or crypto missing:** Encryption is skipped (plain written); decryption of `"encrypted:..."` yields `""` so Core does not crash and simply has no key until the admin fixes config or env.
- **base/base.py import guard:** If `base.auth_api_key_crypto` cannot be imported (e.g. module removed or broken), `base/base.py` falls back to trivial identity functions: `decrypt_auth_api_key(v)` and `encrypt_auth_api_key(v)` that return the value as-is (or normalized). So Core still starts and uses plain keys only.

---

## 6. Using encrypted storage (operational summary)

1. Set **`HOMECLAW_AUTH_KEY`** in the environment to a strong secret (e.g. `openssl rand -base64 32`). Keep it secret; it is needed to decrypt any existing `"encrypted:..."` values.
2. Ensure **`pip install cryptography`** (same as for other features that use `cryptography`).
3. Set or change **auth_api_key** via Portal or `PATCH /api/config/core` (or leave it in config as plain once; the next save through one of the three paths above will encrypt it if env is set).
4. **Restart Core** (and Portal if used) so they load the config and decrypt the key into memory.
5. Clients (Companion, channels) continue to send the **plain** API key in headers; they never see or handle the encrypted form. Encryption is only for the value at rest in `config/core.yml`.

For step-by-step instructions and Companion compatibility, see [RemoteAccess.md](RemoteAccess.md) (“How to store the API key” and “Companion app compatibility”).
