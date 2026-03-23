# Ops Runbook: Mac + Windows Federation

This runbook is for a production-style setup where:

- Operators configure networking and secrets once.
- End users only use the Companion app (no YAML edits, no terminal).

It covers two HomeClaw instances:

- **A:** `AllenPeng-mac-HomeClaw` (Mac)
- **B:** `AllenPeng-win-HomeClaw` (Windows)

---

## 1) Responsibilities split

| Role | What they do |
|------|---|
| Operator/Admin | Configure `instance_identity.yml`, `peers.yml`, `core.yml` flags, service env secrets, health checks |
| End user | Login to Companion, add remote friend, accept request, chat |

---

## 2) One-time operator setup

### 2.1 Instance identity

Set each Core's own identity in `config/instance_identity.yml`.

| Instance | Required keys |
|---|---|
| Mac (A) | `instance_id: AllenPeng-mac-HomeClaw`, `public_base_url`, optional `pairing_inbound_user_id` |
| Win (B) | `instance_id: AllenPeng-win-HomeClaw`, `public_base_url`, optional `pairing_inbound_user_id` |

Use stable `instance_id` values. Do not change them frequently.

### 2.2 Peer roster

Create `config/peers.yml` on each side.

**On Mac (A):**

```yaml
peers:
  - instance_id: "AllenPeng-win-HomeClaw"
    display_name: "AP-Win-HomeClaw"
    base_url: "https://homeclaw.gpt4people.online:9000"
    inbound_user_id: "allenpeng_win_homeclaw"
    api_key_env: "PEER_WIN_KEY"
```

**On Windows (B):**

```yaml
peers:
  - instance_id: "AllenPeng-mac-HomeClaw"
    display_name: "AP-Mac-HomeClaw"
    base_url: "https://mymac.gpt4people.online:9000"
    inbound_user_id: "allenpeng_mac_homeclaw"
    api_key_env: "PEER_MAC_KEY"
```

`api_key_env` is the environment variable name, not the secret value.

### 2.3 Federation flags

Enable these in `config/core.yml` on both instances:

```yaml
federation_enabled: true
federation_e2e_enabled: false
federation_e2e_require_encrypted: false
```

Recommended hardening after rollout:

- Consider enabling `federation_require_accepted_relationship: true`.
- Consider `federation_trusted_instances` allowlist for known instance IDs.

### 2.4 Auth and secrets

If `auth_enabled: true` on a Core, that Core expects inbound API key auth.  
Operators must provide the peer key through service environment.

| Machine | Example env key | Value |
|---|---|---|
| Mac (A) | `PEER_WIN_KEY` | The Windows Core `auth_api_key` value |
| Win (B) | `PEER_MAC_KEY` | The Mac Core `auth_api_key` value |

Do this in service manager (systemd/docker/k8s/Windows service), not per-user shell.

### 2.5 Optional pairing workflow (recommended for easier onboarding)

Use invite CLI so peer entries are generated and imported more safely.

- On recipient Core: `python -m main peer invite-create 3600`
- On initiator Core: `python -m main peer invite-accept <recipient_url> <invite_id> <token> [my_instance_id] [my_display_name]`
- Import returned JSON on both sides: `python -m main peer import <file> [api_key_env_name]`

### 2.6 Verify

- Start both Cores.
- Run `python -m main doctor` on both.
- Confirm each can reach the other's URL.
- Confirm `instance_id` values match exactly between `instance_identity.yml`, `peers.yml`, and `peer_instance_id` references.

---

## 3) User provisioning (operator task)

In each Core's `config/user.yml`, ensure users exist with valid Companion IDs in `im`.

Then add user-type friend entries with remote mapping:

```yaml
friends:
  - name: "Bob (remote)"
    type: user
    user_id: bob
    peer_instance_id: AllenPeng-win-HomeClaw
```

Without `peer_instance_id`, HomeClaw treats `type: user` as local-only.

---

## 4) End-user guide (no config editing)

End users only do this in Companion:

1. Sign in to their normal Core account.
2. Go to **Add friend -> Remote**.
3. Enter remote user's ID + peer instance ID.
4. Open **Friend requests -> Remote** and accept.
5. Start chatting.

If remote chat is rejected, ask admin to verify federation flags, peer roster, and relationship policy.

---

## 5) Operations policy checklist

| Policy | Recommended setting |
|---|---|
| Secret storage | Never store real peer keys in `peers.yml`; use `api_key_env` + deployment secrets |
| Federation switch | `federation_enabled: true` only on nodes intended for cross-instance messaging |
| Relationship enforcement | Enable `federation_require_accepted_relationship` for stricter production policy |
| Transport security | Use HTTPS/Tailscale/secure tunnel between instances |
| Change management | Operators own peer/identity changes; users never edit server config |

---

## 6) Troubleshooting quick map

| Symptom | Likely cause | Fix |
|---|---|---|
| Remote friend appears but cannot send | `federation_enabled` off on one side | Enable on both, restart Core |
| Message says recipient not found/local mismatch | Missing or wrong `peer_instance_id` | Fix friend entry to match `peers.yml` instance ID |
| 401/403 when sending to peer | Wrong peer key wiring | Verify local `api_key_env` name and deployed env value |
| Pairing returns wrong URL | Missing/incorrect `public_base_url` | Set correct public URL in `instance_identity.yml` |
| E2E send fails | E2E required but recipient has no key | Turn off required mode or have recipient register key in Companion |

