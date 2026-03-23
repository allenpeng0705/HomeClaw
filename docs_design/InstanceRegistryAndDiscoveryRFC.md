# RFC: HomeClaw Instance Registry and Discovery

Status: Draft  
Author: HomeClaw design draft (assistant)  
Last updated: 2026-03-23

---

## 1. Problem statement

Today, cross-instance connectivity is explicit and file-driven:

- Each instance defines itself in `config/instance_identity.yml`.
- Operators manually maintain `config/peers.yml`.
- Federation and remote-friend flows work, but onboarding requires YAML and environment secret setup.

This works for advanced users and small deployments, but it becomes hard for:

- non-technical users,
- larger social graphs,
- dynamic environments with changing URLs/IPs,
- managed multi-tenant operations.

We need a simpler way for instances to find, trust, and connect to each other while preserving current peer-to-peer behavior.

---

## 2. Goals

1. **Simple onboarding**: make discovery and connection possible without manual file editing for most users.
2. **Compatibility**: preserve existing `instance_identity.yml`, `peers.yml`, and federation behavior.
3. **Security**: avoid exposing secrets; support strong identity verification and request authorization.
4. **Resilience**: paired instances continue to communicate if registry is temporarily unavailable.
5. **Visibility**: support searchable capability metadata (what an instance can do).
6. **Incremental rollout**: make this optional first, then mature into standard workflow.

---

## 3. Non-goals (v1)

1. Registry does **not** proxy chat payloads between instances.
2. Registry does **not** store user chat/memory content.
3. Registry does **not** replace local trust policy on each Core.
4. Registry does **not** require blockchain or token economics.
5. Registry does **not** remove direct peer mode (manual config still supported).

---

## 4. Key architecture

Two-plane model:

- **Control plane (Registry service)**  
  Registration, discovery, capability listing, invite/request exchange, verification metadata.

- **Data plane (Core-to-Core direct)**  
  Existing federation and `peer_call` traffic remain direct instance-to-instance.

Result: operational UX improves, but runtime message path stays decentralized and robust.

---

## 5. Concepts and entities

### 5.1 Instance record

Represents one HomeClaw Core:

- `instance_id` (stable unique ID),
- `display_name`,
- `public_base_url`,
- `capabilities` (chat/vision/tools/etc.),
- `version_hint`,
- `policy` (public discoverable / private / org-only),
- `status` (online/offline/last_heartbeat),
- verification metadata (signature, verification level).

### 5.2 Peer link

Represents an accepted relationship between two instances, with optional scoped permissions.

### 5.3 Connection request

An invite/request object that allows one instance to request linking with another.

---

## 6. Proposed API surface (Registry)

All endpoints are examples and can be versioned as `/v1/...`.

### 6.1 Registration and heartbeat

- `PUT /v1/instances/{instance_id}/register`
  - Upsert identity metadata and signed proof.
- `POST /v1/instances/{instance_id}/heartbeat`
  - Update liveness and optional health summary.

### 6.2 Discovery

- `GET /v1/instances?query=&capability=&scope=`
  - Search/list instances visible to requester.
- `GET /v1/instances/{instance_id}`
  - Fetch detail for one instance.

### 6.3 Connect/request

- `POST /v1/connect-requests`
  - Create request from source instance to target instance.
- `GET /v1/connect-requests?target_instance_id=...`
  - List pending requests.
- `POST /v1/connect-requests/{id}/accept`
  - Accept and generate peer-link payload.
- `POST /v1/connect-requests/{id}/reject`
  - Reject request.

### 6.4 Export for Core

- `GET /v1/instances/{instance_id}/peer-export`
  - Produce `peers.yml`-compatible objects for direct Core use.

---

## 7. Capability exposure model

Each instance can publish a capability profile:

- high-level categories: `chat`, `vision`, `tools`, `automation`,
- optional detailed capabilities: tool tags, model families, policy tags,
- privacy controls: public summary only vs richer authenticated view.

Companion and admin UI can use this to:

- show discoverable instances,
- filter by function,
- reduce failed connection attempts to incompatible instances.

---

## 8. Security and trust model

### 8.1 Identity and signing

- Each instance has a long-lived signing key pair.
- Registration payloads are signed by the instance private key.
- Registry stores public key and verification status.

### 8.2 Transport and auth

- TLS required for registry traffic.
- Instance auth to registry via short-lived tokens (or mTLS for managed deployments).

### 8.3 Peer authentication

- Core-to-Core requests still require API key / auth policy on receiver.
- Registry can distribute references (key IDs or secret handles), not plaintext secrets.

### 8.4 Trust levels

Suggested levels:

- `unverified`,
- `domain_verified`,
- `org_verified`,
- `manually_trusted`.

Local Core can enforce minimum trust level for incoming federation.

---

## 9. Data model sketch

### 9.1 `instances`

- `instance_id` (PK)
- `display_name`
- `public_base_url`
- `capabilities_json`
- `policy_json`
- `public_key`
- `verification_level`
- `last_heartbeat_at`
- `created_at`, `updated_at`

### 9.2 `connect_requests`

- `request_id` (PK)
- `source_instance_id`
- `target_instance_id`
- `status` (`pending|accepted|rejected|expired`)
- `requested_at`, `resolved_at`
- `message`

### 9.3 `peer_links`

- `link_id` (PK)
- `instance_a`
- `instance_b`
- `state`
- `policy_json`
- `created_at`, `updated_at`

---

## 10. Migration strategy from current model

### 10.1 Phase 0 (today)

- Manual `instance_identity.yml` + `peers.yml`.
- Optional invite CLI flow.
- Federation driven by current flags and user friend links.

### 10.2 Phase 1 (registry optional)

- Add `registry` block to `core.yml` (disabled by default):
  - `registry_enabled`,
  - `registry_url`,
  - `registry_project_id` (optional),
  - `registry_auth_mode`.
- Instance periodically registers and heartbeats.
- Admin can import peer records from registry output.

### 10.3 Phase 2 (UI-integrated)

- Portal/Companion adds "Find instances" and "Connect" screens.
- Accept flow writes to local `peers.yml` automatically (or DB-backed equivalent).

### 10.4 Phase 3 (policy hardening)

- Trust-level enforcement and scoped federation policies.
- Optional signed capability attestations.

Backward compatibility rule: if registry is unavailable, existing direct peer links continue to work.

---

## 11. Failure modes and mitigations

| Failure | Impact | Mitigation |
|---|---|---|
| Registry outage | New discovery/connect flows unavailable | Existing peer links continue direct operation; retry with backoff |
| Stale registry URL | Discovery returns obsolete endpoint | Heartbeat freshness checks and max-age on records |
| Key mismatch | Requests rejected between peers | Key rotation workflow and audit logs |
| Malicious registration spam | Discovery pollution | Rate limiting, verification levels, abuse scoring, moderation |
| Instance ID collision | Routing ambiguity | Signed ownership proof + uniqueness constraints |
| Partial acceptance (one side) | Broken user expectation | Two-phase accept + explicit pending state in UI |

---

## 12. Operational model

### 12.1 Managed cloud registry

- Easiest UX for most users.
- Requires high availability and abuse controls.

### 12.2 Self-hosted registry

- For privacy-focused deployments or enterprise.
- Same protocol, different control ownership.

### 12.3 Hybrid mode

- Public discovery + private allowlist by org/project.

---

## 13. Web3 assessment

Web3 is optional, not required for v1.

### Useful ideas

- Decentralized identifiers (DID-like identity),
- cryptographic attestations,
- signed capability claims.

### Likely overkill early

- blockchain consensus for discovery,
- token economics,
- on-chain metadata writes for dynamic endpoints.

Recommendation: build centralized registry protocol first, with signed identities and portable schema, then evaluate decentralized backends later.

---

## 14. Open questions

1. Should instance discovery be global, org-scoped, or invite-only by default?
2. Where should peer auth secrets live in managed mode (vault, KMS, instance-local only)?
3. Should `peers.yml` remain source-of-truth, or migrate to DB with export compatibility?
4. How should capability claims be validated (self-declared vs verified probes)?
5. How to handle NAT/private deployments where `public_base_url` is unstable?

---

## 15. Suggested next implementation slice

Smallest valuable slice:

1. Add optional `registry` config block.
2. Implement register + heartbeat client in Core.
3. Implement minimal registry service (`register`, `list`, `detail`).
4. Add `peer import from registry` CLI.
5. Add Portal admin page "Discovery (experimental)".

This gives immediate usability gains without touching the existing data plane.

