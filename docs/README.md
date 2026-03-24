# HomeClaw documentation (`docs/`)

This folder is the **source for the public doc site** (MkDocs / Material), published at **[GitHub Pages](https://allenpeng0705.github.io/HomeClaw/)**. Start with **[index.md](index.md)** on the site, or use the sections below.

**Design and internal notes** live in **`docs_design/`** at the repo root (not part of the MkDocs build).

---

## Install & quick start

### 1. Install

| Platform | What to run |
|----------|-------------|
| **Mac / Linux** | Clone the repo, then **`bash install.sh`** or **`./install.sh`** (if needed: `chmod +x install.sh`). |
| **Windows** | **`install.bat`** or **`.\install.ps1`** in PowerShell. If execution policy blocks the script, use `install.bat` or `powershell -ExecutionPolicy Bypass -File .\install.ps1`. |

The script sets up Python dependencies, optional llama.cpp / models guidance, and opens the **Portal** for first-time setup.

- **Full install paths:** [install.md](install.md) · [getting-started.md](getting-started.md) · repo root [InstallationGuide.md](../InstallationGuide.md)
- **After install:** `python3 -m main doctor` — checks config and LLM connectivity

### 2. Run Core

```bash
python3 -m main start
```

Default Core URL: **http://127.0.0.1:9000**. Readiness (when embedding checks finish): `curl http://127.0.0.1:9000/ready`

- **Details:** [run.md](run.md) · [core-config.md](core-config.md)

### 3. Portal (config & onboarding)

```bash
python3 -m main portal
```

Opens **http://127.0.0.1:18472** — users, LLM (`config/llm.yml`), starting Core/channels.

- **Details:** [portal.md](portal.md)

### 4. Chat: Companion app + channels

- **Companion (Flutter):** repo **`clients/HomeClawApp/`** — set Core URL in Settings; add your user from `config/user.yml` or Portal. Same Core as everyone else.
- **WebChat (quick test):** with Core running, `python3 -m channels.run webchat` → browser UI (e.g. port **8014**). Set **`CORE_URL`** in `channels/.env`.

- **Companion:** [companion-app.md](companion-app.md) · [companion-vs-channels.md](companion-vs-channels.md)
- **Channels list:** [channels.md](channels.md) · [channels/README.md](../channels/README.md)
- **Remote access (tunnel / API key):** [remote-access.md](remote-access.md)

---

## Major features (overview)

| Area | What it is | Read more |
|------|------------|-----------|
| **Core** | Single FastAPI backend: LLM loop, memory, tools, skills, plugins, `/inbound`, WebSocket push. | [run.md](run.md), [models.md](models.md) |
| **Mix mode** | Route each turn to local or cloud LLM; usage reports. | [mix-mode-and-reports.md](mix-mode-and-reports.md) |
| **Memory & RAG** | Agent memory, knowledge base, Cognee/Chroma paths (see `config/memory_kb.yml`). | [Cognee-Memory-System-Step-by-Step.md](Cognee-Memory-System-Step-by-Step.md) |
| **Skills & plugins** | OpenClaw-style skills; Python + HTTP plugins in any language. | [plugins.md](plugins.md), [writing-plugins-and-skills.md](writing-plugins-and-skills.md) |
| **ClawHub** | Search/install OpenClaw skills from Portal, Companion, or CLI (`clawhub` on PATH). | [ClawHubLogin.md](ClawHubLogin.md) |
| **Multi-user & sandbox** | `config/user.yml`: users, permissions, per-user file sandboxes. | [per-user-sandbox-and-file-links.md](per-user-sandbox-and-file-links.md) |
| **Friends & social (one Core)** | AI friends + **user-type friends**; user-to-user chat in **Companion** only (Core forwards; no LLM). | [friends-and-family.md](friends-and-family.md), [UserToUserMessagingViaCompanion.md](../docs_design/UserToUserMessagingViaCompanion.md) |
| **Federation (multi-instance)** | Message **remote** user friends across HomeClaw instances: `instance_identity.yml`, `peers.yml`, `federation_enabled` in `core.yml`, optional `federation_trusted_instances` and peer **API keys** for secured Cores. Cross-Core delivery uses **`POST /api/federation/user-message`**; the Companion talks to **your** Core only. Clear-chat can sync to the peer. | [federated-companion-messaging.md](federated-companion-messaging.md), [multi-instance-peers.md](multi-instance-peers.md), [homeclaw-to-homeclaw-and-remote-friends.md](homeclaw-to-homeclaw-and-remote-friends.md), [ops-runbook-mac-win-federation.md](ops-runbook-mac-win-federation.md) |
| **Peer tool (`peer_call`)** | One Core’s LLM can call another Core’s `/inbound` (automation), separate from Companion federation. | [multi-instance-peers.md](multi-instance-peers.md) |
| **Security** | Optional **`auth_enabled`** / API key for inbound and protected APIs; optional Companion app-layer encryption. | [remote-access.md](remote-access.md), [CompanionAppLayerEncryption.md](../docs_design/CompanionAppLayerEncryption.md) |
| **Reliability (messaging)** | Federation uses structured **`error_code`** responses, transport retry on transient failures, and clearer Companion error text; prefer **`core_public_url`** for shareable attachments across instances. | [federated-companion-messaging.md](federated-companion-messaging.md) |

---

## Build & preview the doc site locally

From **repo root**:

```bash
pip install mkdocs-material -e .
mkdocs build    # output in site/
mkdocs serve    # http://127.0.0.1:8000
```

**Diagrams (optional):** SVGs come from **`docs/diagrams/*.mmd`**. From **`docs/`**:

```bash
npm run install:no-browser   # avoids Puppeteer Chrome download issues
npm run diagrams:mac         # macOS + installed Chrome
# Linux/Windows: set PUPPETEER_EXECUTABLE_PATH then run npm run diagrams
```

Or export from [Mermaid Live](https://mermaid.live) into `docs/assets/`.

**Deploy:** push to `main`; GitHub Action **`.github/workflows/docs.yml`** builds and deploys to Pages (Settings → Pages → GitHub Actions).

---

## Repo map

| Path | Role |
|------|------|
| **`docs/`** (this folder) | Public documentation (MkDocs) |
| **`docs_design/`** | Design specs and deep dives |
| **`config/`** | `core.yml`, `llm.yml`, `user.yml`, `peers.yml`, `instance_identity.yml`, … |
| **`AGENTS.md`** (repo root) | Quick reference for developers (ports, tests, known gitignore notes) |
