# Multi-HomeClaw: instance identity, roster, and invite / pairing

**Status:** Shipped (2025-03). Includes: optional **`instance_identity.yml`** / **`peers.yml`**; **`GET /api/instance/identity`**; pairing **create/consume** with **`peer_pairing_enabled`** in **`core.yml`**; dual consume rate limits (**45** POSTs/min + **18** failed checks/min per IP); symmetric **`recipient_import_peer`** when **`initiator_inbound_user_id`** + **`initiator_base_url`** are sent; CLI **`peer import|list`**; tool **`peer_call`**; operator doc **`docs/multi-instance-peers.md`**; doctor hint for **https** peers without **`public_base_url`**; tests **`tests/test_peer_registry.py`**.  
**Related:** [SocialNetworkDesign.md](SocialNetworkDesign.md) (multi-instance future, Core–Core trust), [Design.md](../Design.md) (`POST /inbound`, channels).

---

## 1. Goals

1. **Clear instance identity** — Each HomeClaw Core has a stable, machine-readable identity (distinct from workspace `IDENTITY.md`, which is LLM persona only).
2. **Minimal roster** — A local list of known peer instances (URL + auth + metadata) so a coordinator can **select and connect** without a global discovery service.
3. **Invite / pairing workflow** — A way to add a peer **safely** without hand-editing secrets on both sides (optional UX: CLI, Companion, or admin API later).

**Non-goals (this plan):**

- Global public directory of all HomeClaw instances on the internet.
- Automatic LAN multicast discovery (can be a later optional plugin).
- Full federated social graph (see SocialNetworkDesign for user-to-user across instances).

---

## 2. Concepts

| Term | Meaning |
|------|---------|
| **Instance** | One running HomeClaw Core (one config root, one `host:port`). |
| **`instance_id`** | Stable string, globally unique in *your* deployment (e.g. `home-lab`, `uuid`, or `org/worker-vision`). Used in roster keys and pairing records. |
| **Self identity** | Describes *this* instance (id, display name, optional capabilities for humans/tools). |
| **Roster (peers)** | Local table: for each known peer, how to reach it (`base_url`) and how to authenticate (`user_id` for `/inbound`, API key, etc.). |
| **Pairing** | Time-limited or one-time exchange that **adds or updates** one roster entry without trusting unauthenticated writes long-term. |

**Connection primitive (already in Core):**  
Peer A calls peer B with **`POST {base_url}/inbound`** (or `/local_chat` / `/ws` per existing docs), body includes **`user_id`** allowed in B’s `user.yml`, plus **`text`** (task). Response **`{ "text": "..." }`** is the peer’s reply.

---

## 3. Minimal implementation: clear identity + roster

### 3.1 Files (proposed layout)

Under `config/` (exact names can be adjusted at implement time):

| File | Purpose |
|------|---------|
| **`config/instance_identity.yml`** | **This instance only:** `instance_id`, `display_name`, optional `capabilities` (list of strings for operators/LLM), optional `public_notes`. **No secrets.** |
| **`config/peers.yml`** | **Roster:** list (or map) of peers. Each entry: `instance_id`, `base_url` (HTTPS preferred), `inbound_user_id` (service account on *that* peer), optional `display_name`, optional `capabilities` (cached copy for selection). **Secrets** via env reference or separate `peers_secrets.yml` / keychain (see §3.3). |

If a deployment prefers a single file, `instance_identity.yml` can be merged into `core.yml` under an `instance:` key; the plan recommends a dedicated file for clarity and copy/paste between machines.

### 3.2 Schema sketch (YAML)

**`instance_identity.yml`**

```yaml
instance_id: "home-worker-vision"
display_name: "Vision worker (garage machine)"
# Optional: hints for humans or for a future "peer query" tool
capabilities:
  - vision
  - local_files
# Optional: shown in pairing UI / health
version_hint: "HomeClaw git sha or release tag (manual for now)"
```

**`peers.yml`** (no raw API keys in repo if possible)

```yaml
peers:
  - instance_id: "home-coordinator"
    display_name: "Main house Core"
    base_url: "https://home-coordinator.example.ts.net:8000"
    inbound_user_id: "peer_worker_vision"
    # api_key: use env PEER_KEY_HOME_COORDINATOR or secrets file
    api_key_env: "PEER_KEY_HOME_COORDINATOR"
```

Loader resolves `api_key_env` at runtime; document required env vars in deploy README.

### 3.3 Secrets

- **Peer → Core inbound:** Reuse existing **`auth_enabled`** + API key model for `/inbound` (see Design.md / core config).
- **Service `user_id`:** Each peer defines a dedicated **`user_id`** in `user.yml` with minimal permissions (e.g. only what cross-instance tasks need), or a dedicated “peer” role when that exists.
- **Storage:** Prefer **environment variables** or a **`config/peers_secrets.yml`** in `.gitignore` over committing keys.

### 3.4 Using the roster (coordinator)

- **Manual / tool:** A future built-in or plugin tool `peer_call(instance_id, text)` loads `peers.yml`, resolves URL + key, POSTs `/inbound`, returns `text`.
- **LLM selection:** Optional injection of compact peer list (like LLM catalog) into tool description: `instance_id`, `display_name`, `capabilities`.

### 3.5 Implementation checklist (minimal)

1. Add **`instance_identity.yml`** schema + loader; expose **`instance_id`** on a small **`GET /api/instance/identity`** (or include in existing health/metadata) for pairing verification.
2. Add **`peers.yml`** schema + loader; validate `base_url` and required fields.
3. Document in **`docs/`** or **`Design.md`** snippet: env vars, `user.yml` service accounts, example `curl` peer-to-peer.
4. Optional: **`python -m main doctor`** checks: identity file present, peers URLs reachable (HEAD or `/inbound` ping with probe key).

---

## 4. Invite / pairing workflow

Pairing answers: *“How do I add a peer to `peers.yml` without copying long URLs and keys by hand, and without leaving an open admin API?”*

### 4.1 Threat model (short)

- Pairing must **not** allow arbitrary internet hosts to join the roster without operator intent.
- Tokens should be **short-lived** or **one-time**; prefer **out-of-band** display (QR, paste, local LAN UI).

### 4.2 Roles

| Role | Action |
|------|--------|
| **Initiator (A)** | Wants to call B later; generates **pairing session** on A or B depending on variant. |
| **Acceptor (B)** | Confirms trust; shares or accepts token; results in roster row on A, B, or both. |

### 4.3 Recommended variant: **“Join me” invite from B (acceptor publishes)**

1. Operator on **B** runs: `python -m main peer invite-create` (or Companion button later).
2. Core **B** generates: `invite_token` (random, high entropy), `expires_at` (e.g. 15 minutes), optional `invite_id` for status.
3. B displays **one line** for operator on A: e.g.  
   `homeclaw://pair?v=1&b=https://b.example:8000&t=<token>&i=<invite_id>`  
   or JSON for copy/paste.
4. Operator on **A** runs: `python -m main peer invite-accept --payload '<paste>'`  
   - A’s CLI POSTs to **B**: `POST {B_base}/api/peer/invite/consume` with `invite_token`, plus A’s **`instance_id`**, **`display_name`**, and A’s **inbound callback info** (see below).
5. **B** validates token, records **A** as pending or trusted (operator confirm optional), returns to A: **B’s** `instance_id`, canonical `base_url`, and a **dedicated `inbound_user_id` + API key** for A (or a token scoped to inbound only).
6. **A** writes **`peers.yml`** entry (and stores secret via env or secrets file).  
7. Optionally **B** also adds **A** to its roster (symmetric pairing) using the same pattern in reverse (second invite or piggyback in step 5 response).

**Why acceptor hosts the consume endpoint:** B controls issuance of **its** inbound credentials for A.

### 4.4 Alternative: **pre-shared roster snippet**

For air-gapped or no pairing API yet:

1. B exports **`peer_bundle.yaml`** (unsigned) with `base_url`, `instance_id`, and a **one-time API key**.
2. Operator copies file to A and runs `python -m main peer import peer_bundle.yaml`.
3. Same outcome as manual `peers.yml` edit, but validated and merged.

Pairing API (§4.3) can later produce the same bundle over TLS.

### 4.5 API sketch (on Core, gated)

All behind **`auth_enabled`** + admin API key or local-only binding:

| Endpoint | Purpose |
|----------|---------|
| `POST /api/peer/invite/create` | Create invite; returns payload for other operator. |
| `POST /api/peer/invite/consume` | Other instance sends token + its identity; returns peer connection material. |
| `GET /api/instance/identity` | Read-only **self** `instance_id` + `display_name` for verification display. |

**Rate limit** and **single-use** tokens mandatory on `consume`.

### 4.6 Implementation checklist (pairing)

1. Implement **invite create / consume** with in-memory or SQLite store (invite rows: token hash, expiry, consumed_at). *(Done: `database/peer_invites.json` + hashed token.)*
2. CLI **`peer invite-create`**, **`peer invite-accept`**, **`peer import`** (merge JSON/YAML into `peers.yml`), **`peer list`**.
3. Log audit line: paired `instance_id`, timestamp, operator user (if available).
4. Document **Tailscale / HTTPS** requirement for non-loopback pairing.
5. Companion UI: later; CLI first.

---

## 5. Phasing summary

| Phase | Deliverable |
|-------|-------------|
| **P0** | Plan doc (this file) + align names with `SocialNetworkDesign.md`. |
| **P1** | `instance_identity.yml` + `peers.yml` + loader + `GET /api/instance/identity` + docs + doctor checks. |
| **P2** | Tool or plugin **`peer_call`** (or equivalent) using roster. |
| **P3** | Invite create/consume API + CLI pairing flow. |
| **P4** (optional) | External directory service; LAN discovery plugin. |

---

## 6. Open questions

- **Symmetric vs one-way roster:** Many setups only need coordinator → worker; workers may not need coordinator in `peers.yml` unless callbacks are required.
- **Capability negotiation:** Roster `capabilities` can be **operator-maintained** at P1; optional **POST /api/instance/capabilities** on each Core later for auto-refresh.
- **Naming collision:** Enforce unique `instance_id` within a fleet; global uniqueness is organizational.

---

## 7. Changelog

| Date | Change |
|------|--------|
| 2025-03-22 | Initial plan: minimal identity + roster + invite/pairing workflow. |
| 2025-03-22 | Implemented: `base/peer_registry.py`, routes under `/api/instance/identity` and `/api/peer/invite/*`, `peer_call` tool, `main peer` CLI, doctor checks, example YAML files. |
| 2025-03-22 | Added: `peer import` / `peer list`, dual per-IP consume rate limits (45/min all attempts + 18/min failed verifies). |
