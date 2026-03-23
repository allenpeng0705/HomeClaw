# Multi-instance: peers, pairing, and `peer_call`

When you run **more than one HomeClaw Core** (different machines or ports), you can treat each Core as a **peer**: one instance calls another over HTTP using the same contract as channels — **`POST /inbound`**.

This page is the **operator guide**. Design details live in [MultiInstanceIdentityRosterAndPairing.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/MultiInstanceIdentityRosterAndPairing.md) in the repo.

---

## What you configure

| File | Purpose |
|------|---------|
| **`config/instance_identity.yml`** | Stable **`instance_id`**, display name, optional **`public_base_url`**, optional **`pairing_inbound_user_id`**. Copy from **`config/instance_identity.yml.example`**. |
| **`config/peers.yml`** | Roster of other Cores: **`instance_id`**, **`base_url`**, **`inbound_user_id`**, optional **`api_key_env`**. Copy from **`config/peers.yml.example`**. |

**Workspace `IDENTITY.md`** is only LLM persona text — it is **not** the same as instance identity for networking.

---

## `public_base_url` (important for HTTPS and pairing)

When another machine calls **`/api/peer/invite/consume`**, the response includes a **`peer.base_url`** for *this* Core. That URL is built from:

1. **`public_base_url`** in `instance_identity.yml` (best), else  
2. **`Host`** / **`X-Forwarded-*`** headers on the request.

If you use **HTTPS** or a reverse proxy, set **`public_base_url`** explicitly (e.g. `https://homeclaw.example.ts.net:9000`) so partners get a correct URL in **`peers.yml`**.

**Doctor** warns if **`peers.yml`** lists **`https://`** peers but **`public_base_url`** is missing.

---

## Security

- **`peer_pairing_enabled`** in **`config/core.yml`**: when **`false`**, **`POST /api/peer/invite/create`** and **`POST /api/peer/invite/consume`** return **404** (`peer_pairing_disabled`). Use on nodes that must not accept pairing.
- **`POST /api/peer/invite/consume`** is rate-limited per client IP: **all attempts** (default **45/min**) and **failed token checks** (default **18/min**, then **429**).
- Peers still need an **API key** for **`/inbound`** when **`auth_enabled: true`** — use **`api_key_env`** in **`peers.yml`** and set the variable in the environment (avoid committing keys).

---

## Pairing flow (invite)

**On Core B (recipient)** — Core running, operator with API key if auth is on:

```bash
python -m main peer invite-create [ttl_seconds]
```

Share **`invite_id`**, **`token`**, and B’s base URL with the operator on A.

**On machine A (initiator)**:

```bash
python -m main peer invite-accept https://B:9000 <invite_id> <token> [my_instance_id] [my_display_name]
```

A’s **`instance_identity.yml`** should define **`public_base_url`**, **`instance_id`**, **`display_name`**, and **`pairing_inbound_user_id`**: the **`user_id`** that B will use when calling A’s **`/inbound`**. That user must exist in **`config/user.yml`** on A with **`IM`** (or whatever your setup requires for inbound).

**Save the JSON response** from `invite-accept`:

- **On A**: `python -m main peer import saved.json [API_KEY_ENV]` — merges the top-level **`peer`** (B) into A’s **`peers.yml`**.
- **On B** (symmetric): if the response includes **`recipient_import_peer`**, save the full JSON (or that object) and run **`peer import`** on **B** to add A to B’s **`peers.yml`**.

Set **`api_key_env`** on import when the key is not in the file:  
`python -m main peer import b.json PEER_KEY_B`

---

## CLI reference

| Command | Role |
|--------|------|
| `python -m main peer invite-create [ttl]` | Create invite (local Core must be up). |
| `python -m main peer invite-accept <B_url> <id> <token> …` | Consume invite on B. |
| `python -m main peer import <file> [api_key_env]` | Merge **`peer`** or **`recipient_import_peer.peer`** into **`peers.yml`**. |
| `python -m main peer list` | Print configured peers as JSON. |

---

## Tool: `peer_call`

The main LLM can call **`peer_call`** with **`text`** and **`instance_id`** (from **`peers.yml`**) to send a message to another Core’s **`/inbound`**. Sub-agents spawned with **`sessions_spawn`** do not get tools; only the main agent uses **`peer_call`**.

Optional prompt injection: **`tools.peer_roster_inject_enabled`** / **`peer_roster_inject_max_chars`** in **`config/skills_and_plugins.yml`** (see [Core config](core-config.md)).

---

## Checklist

1. **`instance_id`** set on each Core.  
2. **`user.yml`** on each Core: service **`user_id`** for the other side’s **`inbound_user_id`**.  
3. **`public_base_url`** when using HTTPS or pairing behind proxies.  
4. **`pairing_inbound_user_id`** on the initiator so symmetric **`recipient_import_peer`** is complete.  
5. Run **`python -m main doctor`** after changes.

---

## Future: Companion user-to-user across instances

**Today:** **`peer_call`** is for the **AI** on one Core to call another Core’s **`/inbound`**. It is **not** Companion peer-to-peer chat.

**Planned (design only):** Federated social messaging — same **Companion → Core → … → Companion** path as [user-to-user on one instance](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/UserToUserMessagingViaCompanion.md), extended so Cores relay when the friend lives on another instance. The plan keeps **existing `user-message` / inbox behavior** unless **`federation_enabled`** and optional **`peer_instance_id`** on friends are added.

See **[FederatedCompanionUserMessaging.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/FederatedCompanionUserMessaging.md)** (phased P0–P5, non-breaking rules).

---

## See also

- [Core config (`core.yml`)](core-config.md) — **`peer_pairing_enabled`**, auth, tools.  
- [Remote access](remote-access.md) — tunnels and **`auth_enabled`**.  
- [LLM catalog how-to](llm-catalog-howto.md) — model refs (separate from peers).
