# HomeClaw-to-HomeClaw vs Remote Friends

This page summarizes two related but different multi-instance features:

1. **HomeClaw-to-HomeClaw** (AI calls another Core with `peer_call`)
2. **Companion remote friends** (user-to-user messaging across Cores via federation)

---

## Quick distinction

| Topic | HomeClaw-to-HomeClaw (`peer_call`) | Companion remote friends (federation) |
|------|---|---|
| Primary use | AI on Core A asks Core B to do a task | Human user on Core A chats with human user on Core B |
| Initiator | Main LLM/tool layer | Companion app user |
| Transport | Core A -> Core B `POST /inbound` | Core A -> Core B federation user-message APIs |
| Depends on | `instance_identity.yml`, `peers.yml`, tool access | `instance_identity.yml`, `peers.yml`, `federation_*` flags, user friend links |
| Same as sub-agent? | No (`sessions_spawn` is local one-off in same Core) | No |

---

## Core files and what they mean

| File | Scope | What it defines |
|------|---|---|
| `config/instance_identity.yml` | This Core only | Who this instance is (`instance_id`, `display_name`, optional `public_base_url`, optional `pairing_inbound_user_id`) |
| `config/peers.yml` | This Core's roster | Which remote Cores this instance can call (`instance_id`, `base_url`, `inbound_user_id`, optional `api_key_env`) |
| `config/core.yml` | This Core behavior | Feature flags such as `peer_pairing_enabled`, `federation_enabled`, and federation security policy |
| `config/user.yml` | Per user/friend graph | Local and remote user friends (`type: user`, optional `peer_instance_id`) for Companion messaging |

---

## Flag reference (`config/core.yml`)

| Flag | Applies to | Default intent | Behavior when enabled |
|------|---|---|---|
| `peer_pairing_enabled` | Pairing APIs | Allow easier peer onboarding | Enables invite create/consume APIs for peer pairing |
| `federation_enabled` | Remote friends | Master switch | Enables cross-instance user-to-user path |
| `federation_trusted_instances` | Remote friends | Optional allowlist | If non-empty, inbound federation only from listed `instance_id` values |
| `federation_require_accepted_relationship` | Remote friends | Stronger trust policy | Requires accepted relationship state, not just YAML links |
| `federation_e2e_enabled` | Remote friends | Optional privacy layer | Enables `hc-e2e-v1` envelope support and Companion key registration flow |
| `federation_e2e_require_encrypted` | Remote friends | Strict privacy mode | Federated user messages must be encrypted (plaintext rejected) |

---

## Behavior matrix (remote friends)

| `federation_enabled` | `federation_e2e_enabled` | `federation_e2e_require_encrypted` | Result |
|---|---|---|---|
| false | any | any | Remote friends across instances are disabled |
| true | false | false | Remote friends work in plaintext |
| true | true | false | Remote friends work; E2E is optional when keys are available |
| true | true | true | Remote friends require E2E envelopes (current encrypted path is text-focused) |

---

## Typical request flow

### A) HomeClaw-to-HomeClaw (`peer_call`)

| Step | Description |
|---|---|
| 1 | Main LLM decides to use `peer_call` |
| 2 | Tool resolves target from `peers.yml` (`instance_id`, `base_url`, `inbound_user_id`, auth) |
| 3 | Core sends `POST /inbound` to remote Core |
| 4 | Remote Core handles request as inbound user and returns response |

### B) Companion remote friends (federation)

| Step | Description |
|---|---|
| 1 | User opens remote friend chat in Companion |
| 2 | Local Core validates federation flags, peer mapping, and relationship policy |
| 3 | Local Core forwards message to peer Core federation endpoint |
| 4 | Peer Core validates sender/relationship and delivers to recipient inbox |
| 5 | Recipient sees message in Companion thread (optional E2E decrypt on device) |

---

## Config checklist (operator)

| Item | For `peer_call` | For remote friends |
|---|---|---|
| Unique `instance_id` per Core | Required | Required |
| Correct `public_base_url` | Recommended (important behind proxy/tunnel) | Recommended |
| `peers.yml` on both sides | Required for practical two-way calls | Required |
| Valid `inbound_user_id` mapping | Required | Not primary, but keep peer config correct |
| `federation_enabled: true` on both | Not required | Required |
| Remote friend request/accept flow | Not required | Required in normal secure setup |
| Optional E2E flags | Not used | Optional/required depending on policy |

---

## Common mistakes and fixes

| Mistake | Why it breaks | Fix |
|---|---|---|
| Putting API key value directly in `api_key_env` | `api_key_env` expects an env variable name, not secret value | Set `api_key_env: "PEER_KEY_X"` and export `PEER_KEY_X=...` |
| `instance_id` mismatch between files | Peer lookup and friend routing rely on exact IDs | Keep `instance_identity.yml` and `peers.yml` IDs consistent |
| Forgetting `peer_instance_id` on remote user friend | System treats friend as local user | Add `peer_instance_id` in friend entry |
| Enabling strict E2E without key readiness | Messages can be rejected | Enable E2E first, verify key registration, then require encryption |
| Assuming `sessions_spawn` is cross-instance | `sessions_spawn` is local one-off model run | Use `peer_call` for AI cross-instance tasks |

---

## Your current conceptual model (confirmed)

- `instance_identity.yml` = **my own HomeClaw identity**
- `peers.yml` = **other HomeClaw instances I connect to**
- `peer_call` = **AI-to-AI/Core-to-Core task call**
- federation remote friends = **human user chat across instances**

