# HomeClaw Improvement Ideas (Learning from other agent)

This document summarizes the [other agent](https://github.com/other-agent/other-agent) project, compares it with HomeClaw, and records improvement ideas so HomeClaw can evolve into a stronger **home agent accessible anywhere**.

---

## 1. other agent Summary

other agent is a **personal AI assistant** you run on your own devices. Source was reviewed in `../clawdbot` (clone of other-agent/other-agent).

### 1.1 Core Idea

- **Local-first Gateway**: One control-plane process (WebSocket + HTTP on a single port, default 18789). Channels, CLI, WebChat, and companion apps all connect to this gateway.
- **Multi-channel inbox**: WhatsApp, Telegram, Slack, Discord, Google Chat, Signal, BlueBubbles (iMessage), iMessage (legacy), Microsoft Teams, Matrix, Zalo, Zalo Personal, WebChat. Same assistant behind every channel.
- **Cloud AI by default**: Optimized for Anthropic (Claude Pro/Max, Opus) and OpenAI (ChatGPT/Codex) via OAuth or API keys. Other providers (OpenRouter, Ollama, etc.) are supported; local models are optional.
- **Agent as “Pi” runtime**: Single embedded agent (pi-mono–derived) with a **workspace** (`AGENTS.md`, `SOUL.md`, `TOOLS.md`, etc.), **sessions** (JSONL per session), and **skills** that teach the model how to use tools.
- **First-class tools to control your environment**:
  - **Exec**: Run shell commands (sandbox / gateway host / remote node), with approval gating and timeout.
  - **Browser**: Dedicated Chrome/Chromium, snapshots, actions (MCP-style).
  - **Canvas**: Agent-driven visual workspace (A2UI) on macOS/iOS/Android.
  - **Nodes**: Companion devices (macOS/iOS/Android or headless) that expose `camera`, `screen.record`, `location.get`, `system.run`/`system.notify` on the device.
- **Skills**: AgentSkills-compatible `SKILL.md` in bundled / managed (`~/.other-agent/skills`) / workspace (`<workspace>/skills`) with gating (bins, env, config). ClawHub is a public skill registry (install/update/sync).
- **Security**: DM pairing (unknown senders get a code; approve via CLI). Allowlists per channel. Sandbox for non-main sessions (Docker). Exec approvals for gateway/node host.
- **Remote access**: Tailscale Serve/Funnel or SSH tunnels; gateway can bind loopback and be reached via tunnel. “Remote Gateway” runbook for running gateway on Linux while using device nodes for local actions.
- **Onboarding**: CLI wizard (`other-agent onboard`) for gateway, workspace, channels, daemon, skills. `other-agent doctor` for config/health.

### 1.2 Architecture (Simplified)

```
Channels (WhatsApp, Telegram, …) → Gateway (WS + HTTP, one port)
                                        ├── Pi agent (RPC, workspace, sessions)
                                        ├── Tools (exec, browser, canvas, nodes, cron, …)
                                        ├── Skills (SKILL.md, gating)
                                        ├── CLI / WebChat / macOS app / iOS·Android nodes
                                        └── Config (other-agent.json), pairing, allowlists
```

- **Gateway** = control plane: routing, sessions, presence, config, cron, webhooks, Control UI.
- **Channels** push inbound messages into the gateway; gateway routes to an agent (main or per-channel/group); agent uses tools and skills; reply is sent back through the same (or configured) channel.
- **Nodes** are peripherals: they connect over WS and execute device-local commands (`node.invoke`); they do not run the gateway.

---

## 2. HomeClaw vs other agent (Comparison)

| Aspect | HomeClaw | other agent |
|--------|------------|----------|
| **Primary LLM** | Local (llama.cpp) + optional cloud (LiteLLM) | Cloud (Anthropic/OpenAI) + optional local (e.g. Ollama) |
| **Channels** | Email, Matrix, Tinode, WeChat, WhatsApp, CLI | WhatsApp, Telegram, Slack, Discord, Google Chat, Signal, iMessage, BlueBubbles, Teams, Matrix, Zalo, WebChat, CLI |
| **Access from anywhere** | Yes (email/IM to home core) | Yes (same; plus Tailscale/SSH for gateway UI) |
| **Control plane** | Core (FastAPI, HTTP); channels are separate processes that POST to core | Single Gateway (WS + HTTP one port); channels run inside or connect to gateway |
| **Memory** | RAG (SQLite + Chroma), chat history, session/run IDs | Session transcripts (JSONL), workspace bootstrap files (AGENTS.md, SOUL.md, …) |
| **Extensibility** | Plugins (Python, description-based routing when orchestrator on) | Skills (SKILL.md, AgentSkills-compatible), plugins/extensions |
| **“Agent” capabilities** | Chat + RAG + optional plugin (e.g. Weather, News) | Chat + **tools**: exec, browser, canvas, nodes, cron, webhooks, sessions_* (agent-to-agent) |
| **Device control** | Not yet | Nodes: camera, screen, location, system.run/notify; exec on gateway or node |
| **Onboarding** | Manual config (YAML), CLI in main.py | Wizard (`other-agent onboard`), `other-agent doctor` |
| **Remote exposure** | Channels reach core (host/port); no built-in tunnel story | Tailscale Serve/Funnel, SSH tunnel, auth (token/password) |
| **Multi-agent / sessions** | Single core; user/session/run for chat and memory | Multi-agent routing (workspace per agent), session model (main vs group, activation, queue) |

**Similarities**: Both are personal assistants you self-host; both use multiple channels to talk to “one” assistant from anywhere; both have a central brain (Core vs Gateway) and some form of memory/session.

**Major differences**: other agent is **tool- and skill-heavy** (exec, browser, nodes, skills registry) and **cloud-AI–first**; HomeClaw is **local-LLM–first** with **RAG memory** and **lightweight plugins**. other agent has a single Gateway process and rich onboarding/ops; HomeClaw has Core + separate channel processes and YAML config.

---

## 3. Improvement Ideas: Toward a “Home Agent, Accessible Anywhere”

Goal: Keep HomeClaw’s **local-first and RAG** identity while making it more of a **home agent** that can **act on your behalf** and stay **easy to reach from anywhere**. Ideas below are inspired by other agent and adapted to HomeClaw’s stack.

### 3.1 Tool Layer (Agent That Can “Do Things”)

- **Introduce a small tool/exec layer** (opt-in, permission-gated):
  - Allow the core (or a dedicated plugin) to run **shell commands** or **scripts** on the host (e.g. “list my downloads”, “run backup script”). Start with an allowlist of commands or scripts and optional approval (similar to other agent’s exec approvals).
  - This makes the assistant a “home agent” that can perform actions on the machine it runs on.
- **Optional “node” concept** (later): A lightweight agent on another device (e.g. Raspberry Pi) that reports status or runs simple commands and is reachable from the core. No need to match other agent’s full node protocol initially; a minimal HTTP or queue-based interface is enough.

### 3.2 Skills / Plugin Discovery and Descriptions

- **Reuse plugin descriptions for routing** (HomeClaw already has this when orchestrator is on): Ensure every plugin exposes a clear, concise description so the LLM can route user intents reliably.
- **Skill-like docs for plugins**: Optional `SKILL.md` or `README.md` in each plugin folder with a short description and example prompts (similar to other agent’s SKILL.md). Core or a script can aggregate these for prompt injection or discovery.
- **Simple “skill registry”** (later): A list (file or static page) of available plugins/skills and how to enable them, so users and contributors know what the home agent can do.

### 3.3 Onboarding and Health

- **CLI wizard**: A single entry point (e.g. `python main.py setup` or `homeclaw onboard`) that guides: config path, core host/port, main/embedding model choice, one channel (e.g. email or CLI), and optional memory/RAG. Output: minimal `core.yml` / `llm.yml` / `user.yml` (or equivalent).
- **Doctor command**: `homeclaw doctor` (or similar) that checks: core reachable, LLM and embedding endpoints healthy, config valid, channel credentials if configured. Print clear next steps.
- This reduces friction for “install at home and use from anywhere” without copying other agent’s full stack.

### 3.4 Remote Access and Security

- **Document “access from anywhere”**: One page that explains: (1) channels (email/IM) already allow remote access; (2) if users expose core directly (e.g. for a future WebChat), recommend Tailscale or SSH tunnel and auth (token/password or reverse proxy).
- **Channel allowlists**: HomeClaw already has `user.yml` and permission checks. Make allowlists very explicit in docs (e.g. “only these emails/IM IDs can talk to the core”) and optionally add a small pairing step (e.g. first contact gets a code, user confirms in config or CLI).
- **DM pairing (optional)**: For IM channels, consider a pairing flow for unknown senders (code in reply, approve via CLI or config) so the home agent is not open to anyone who finds the number/id.

### 3.5 Single Entry Point and Daemon

- **Single process or single “start” command**: Option to run core and one or more channels from one process or one script (e.g. `main.py start --with-email`) so deployment is “run this and you have core + channel”. other agent’s single Gateway is appealing for ops; HomeClaw can keep Core + channels as separate processes but present one logical entry point.
- **Daemon / service**: Document or provide a simple way to run HomeClaw as a service (systemd, launchd, or a small wrapper) so the home agent stays on after logout.

### 3.6 WebChat and Dedicated Channel

- **WebChat**: A minimal web UI that talks to the core (same `PromptRequest` / response contract as other channels) so users can chat from a browser on the LAN (or over Tailscale/SSH). No need for full Control UI; just “message core and show reply”.
- **Dedicated HomeClaw channel**: Later, a small PWA or app that uses the same core API and optionally supports voice or device actions, reinforcing “one home agent, many ways in.”

### 3.7 Session and Multi-User Clarity

- **Session/conversation model**: HomeClaw already has session_id and run_id for chat and memory. Document the model clearly (e.g. one session per user_id per channel, or per app_id) so plugins and future tools behave consistently.
- **Multi-user / multi-agent** (later): If multiple people or “agents” use the same core, consider namespacing by user or workspace (like other agent’s per-agent workspace) so RAG and plugins can be scoped.

### 3.8 What to Keep from HomeClaw

- **Local LLM first**: Keep llama.cpp and LiteLLM as the main story; optional cloud is a strength for privacy and cost.
- **RAG memory**: Keep SQLite + Chroma and the current memory pipeline; it differentiates HomeClaw from other agent’s transcript + bootstrap approach.
- **Simple stack**: Keep deployment simple (Python, SQLite, Chroma, minimal deps); add tools and onboarding without requiring a full Node/TypeScript stack.
- **Plugins**: Keep the plugin model; align it with “skills” only where it helps (descriptions, discovery, optional SKILL.md).

---

## 4. Suggested Priority (Short Term)

1. **Document** “access from anywhere” and channel allowlists (and optional pairing) in the main docs or Design.md.
2. **CLI wizard** for first-time setup (config + one channel + health check).
3. **Doctor command** for config and endpoint health.
4. **Optional exec/shell tool** (allowlist + approval) so the home agent can run safe commands on the host.
5. **Minimal WebChat** that reuses the core’s HTTP API so users can chat from the browser without configuring another channel.

---

## 5. Channel vs Gateway, and the IM Login / Remote-Access Problem

This section records the discussion: should we refine the channel vs gateway design, and how does other agent (or alternatives) simplify “computer must log in and stay a friend” for IM channels?

### 5.1 Channel vs Gateway in HomeClaw Today

- **Core** = the brain: request handling, RAG, LLM calls, plugin routing. One FastAPI process; channels talk to it over HTTP (`POST /process`, `POST /local_chat`).
- **Channels** = adapters: each channel (email, Matrix, WeChat, WhatsApp, CLI) is a separate process or entry point that (1) receives user messages from the outside world, (2) builds a `PromptRequest`, (3) POSTs to the Core, (4) receives the response (sync or via callback) and sends it back to the user.

So the “gateway” in HomeClaw is effectively the **Core**; “channels” are **clients of the Core** that run elsewhere (or on the same machine). other agent instead runs **one Gateway process** that **embeds** all channel clients (WhatsApp, Telegram, etc.) inside it — so there is a single deployment unit and one port.

**Refinement options (optional):**

- **Keep current split**: Core and channels stay separate processes. Easiest for adding new channels without touching the Core. Downside: more processes to start and monitor.
- **Single-process option**: Run Core + selected channels in one process (e.g. Core starts an email poller and an optional WebChat server). One command, one place to look for logs. We can add this as an option without removing the current “channel as separate process” model.
- **Naming**: We can explicitly call the Core the “Gateway” in docs (like other agent) so “Gateway = single control plane; channels = ways to reach it” is clear.

No need to copy other agent’s single binary; the important part is **one clear control plane** and **one logical way to start** the system (even if that starts several processes).

### 5.2 The Problem: IM Login and “Be a Friend”

For IM-based channels (WeChat, WhatsApp, etc.) the **computer** (home machine) must:

1. **Log in** to the IM as some identity (user account or bot).
2. **Keep that login alive** (session persistence; re-QR or re-auth when it drops).
3. Be **discoverable** by the mobile user — i.e. the mobile user must “add” or “talk to” that identity (so the computer is “one friend” or “the bot”).

That’s inherently fiddly: session storage, reconnection, and sometimes ToS or platform limits (e.g. unofficial WhatsApp clients). So the question is: how does other agent simplify this, and what alternatives exist (own IM app + backend vs server to publish home IP for P2P)?

### 5.3 How other agent Handles It (They Don’t Build a Proxy or P2P Server)

other agent **does not** run a relay server to proxy messages, and **does not** run a server to publish the home computer’s IP for P2P. They simplify the problem in three ways:

**1. Prefer “bot” channels (no “login as user”)**

- **Telegram, Discord, Slack, Google Chat, Matrix (bot), etc.**: You create a **bot** (e.g. via BotFather for Telegram), get a **token**, put it in config. The Gateway runs the **bot client** (long polling or webhook). The user **adds the bot** as a contact or adds it to a group. So:
  - The “computer” is the **bot**; there is no “your personal account logged in on the computer.”
  - One-time setup: get token → configure → start Gateway. No QR, no “keep my WhatsApp logged in.”
- **Email**: Same idea: one identity (SMTP/IMAP) for the agent; user sends to that address. No “friend” in the IM sense.

**2. WhatsApp: dedicated number or multi-device link**

- other agent uses **Baileys** (WhatsApp Web–style client). Two patterns:
  - **Dedicated number (recommended)**: Use a **second number** (or WhatsApp Business) for the Gateway. The Gateway logs in as that number once (QR or session); session is stored in `~/.other-agent/credentials`. The user **adds that number** as a contact. So the computer is “the bot’s number,” not “your phone on the computer.”
  - **Personal number**: Link the Gateway as a **multi-device** companion to your phone (QR once; session stored). Then the Gateway is “your WhatsApp on the computer”; you can self-chat or use it as a second device. Session persistence is still a real-world issue (re-QR sometimes), but it’s a known tradeoff.

So for WhatsApp they **do** have “computer must login and keep status,” but they **reduce** the “friend” problem by treating the Gateway as a **separate identity** (dedicated number) or as your **second device** (multi-device). They don’t introduce a proxy server.

**3. WebChat: no IM at all**

- The Gateway serves **WebChat** (and Control UI) over the same port. To use it from **mobile**, you don’t use any IM: you **reach the Gateway** over **Tailscale** (or VPN) or **SSH tunnel**. So:
  - No IM client on the computer for that path; no “friend” or login.
  - Remote access = “make the Gateway reachable” (Tailscale Serve, or `ssh -L 18789:127.0.0.1:18789 user@home`), then open the dashboard in the browser on your phone.

So other agent’s “simple” path for “access from anywhere” is: **use bot channels** (token only) **or** **use WebChat + Tailscale/SSH** (no IM). The harder path (WhatsApp with a persistent session) they support but recommend a dedicated number and accept that session maintenance is part of ops.

### 5.4 Options for HomeClaw

| Approach | Pros | Cons |
|----------|------|------|
| **A. Bot-first channels** | No “login as user”; one token per channel; user adds bot. Telegram, Discord, Matrix bot, etc. fit this. Email is similar (one agent identity). | WeChat/WhatsApp “personal” still need QR or dedicated number + session handling. |
| **B. WebChat + Tailscale/SSH** | No IM setup for “access from anywhere.” User reaches Core over VPN/tunnel and uses a minimal Web UI. No proxy server. | User must set up Tailscale or SSH once; not “just open WhatsApp.” |
| **C. Own IM app + backend server** | You control the protocol; no third-party IM session or ToS. Mobile app talks to your server; server forwards to home Core. | You build and operate the app and server; discovery, auth, and reliability are on you. other agent did not choose this. |
| **D. Lightweight “discovery” server** | Server only publishes “home Core’s current reachable address” (or helps with NAT traversal) so the mobile client can open a direct connection (e.g. WebChat or a small app) to the Core. No message content on the server. | Still need a small client (browser or app) that talks to the Core; server is only for discovery/connectivity. Simpler than a full message proxy. |

**Recommendation (aligned with other agent):**

- **Short term**: Prefer **bot-style or email-style** channels where the Core has **one identity** (bot token or email account); document **WebChat + Tailscale/SSH** as the “no IM” way to reach the Core from anywhere. That avoids building a proxy or P2P server and keeps the “computer = one identity” model.
- **If you want “one app to rule them all” later**: A **dedicated HomeClaw app** that talks **directly to the Core** (like WebChat) and uses a **discovery helper** (optional small server or Tailscale) only to find the Core’s address is a reasonable next step — closer to (D) than to (C). Full own-IM + backend (C) is a much bigger commitment and other agent explicitly did not go that route.

### 5.5 Summary

- **Channel vs Gateway**: We can keep Core = control plane and channels = adapters; optionally add a single-process or single-command start, and use “Gateway” in docs for clarity. No need to merge everything into one binary.
- **Login / friend**: other agent simplifies by (1) **bot channels** (token only), (2) **WhatsApp** as dedicated number or multi-device with stored session, (3) **WebChat** so “from anywhere” can mean “Tailscale/SSH + browser” with no IM. They do **not** use a message proxy server or a P2P discovery server.
- **HomeClaw**: Favor bot/email channels and WebChat + Tailscale/SSH first; consider a dedicated app + optional discovery server later if you want to avoid depending on third-party IM at all.

---

## 6. Making Different Bots Easily (Inbound API + Webhook)

To avoid implementing every IM channel from scratch, HomeClaw now supports a **minimal contract** so any bot can connect to the Core with a few lines of code.

### 6.1 Core `POST /inbound` (minimal JSON → sync reply)

The Core exposes:

```http
POST /inbound
Content-Type: application/json

{ "user_id": "<id>", "text": "<message>", "channel_name?": "telegram", "user_name?": "Alice" }
```

Response: `{ "text": "<reply>" }`. Permission is checked via `config/user.yml` (add `user_id` to a user with `IM` permission).

- **No channel process required**: Your Telegram/Discord/custom bot can POST directly to the Core if the Core is reachable (e.g. same host or Tailscale).
- **One integration pattern**: Receive message in your bot → POST to `http://<core>/inbound` → send `response.text` back to the user.

### 6.2 Webhook channel (optional relay)

If the Core is not publicly reachable, run the **webhook** channel; it accepts the same minimal JSON and forwards to Core `/inbound`:

```bash
python -m channels.webhook.channel   # listens on 8005 by default
```

Then point your bot at `http://<webhook_host>:8005/message` instead of the Core. Same request/response shape.

### 6.3 Adding a new bot (e.g. Telegram, Discord)

1. Create a bot with the platform (BotFather, Discord Developer Portal, etc.) and get a token.
2. Write a small script or use a framework: on message → `POST http://<core_or_webhook>/inbound` with `user_id` (e.g. `telegram_<chat_id>`), `text`, and optional `channel_name`.
3. Add that `user_id` (or a pattern) to `config/user.yml` under a user with `IM` permission.
4. No new code in the HomeClaw repo; the “channel” is your script + the shared `/inbound` API.

See `channels/webhook/README.md` for minimal Telegram and Discord examples.

### 6.4 Full channel (when you need async or registration)

When you need the Core to push replies to your process (async) or to register as a first-class channel, implement `BaseChannel`: start a server with `/get_response`, register with the Core, and use `POST /process` instead of `/inbound`. Use `/inbound` (or the webhook) when a **sync** request/response is enough.

### 6.5 HTTP vs WebSocket (when to use which)

| Use case | API | Why |
|----------|-----|-----|
| **Any external bot** (Telegram, Discord, Slack, n8n, …) | **HTTP POST /inbound** (or webhook `/message`) | One request per message, sync reply. Bots don’t hold a long-lived connection to us; they send an HTTP request when the user sends a message. |
| **Our own client** (WebChat, dedicated app) | **WebSocket /ws** | One persistent connection; send `{"user_id", "text"}`, receive `{"text"}`. Use for a future WebChat UI or streaming later. Same permission as `/inbound` (user_id in config/user.yml). |

So: **webhook (HTTP) for bots**; **WebSocket for our own client** when we want a single connection or future streaming. other agent uses WebSocket for the control plane (CLI, WebChat, nodes); we use HTTP for “any bot” and add WS for our own client.

### 6.6 Example: Telegram channel

A full minimal example lives in **`channels/telegram/`**:

- **`channel.py`**: Long-polls Telegram `getUpdates`, for each message POSTs to Core `/inbound`, sends reply back.
- **`README.md`**: Setup (BotFather, .env, user.yml), run, and short note on HTTP vs WS.
- **`.env.example`**, **`requirements.txt`**: For standalone install.

Run: start Core, then `pip install -r channels/telegram/requirements.txt` and `python -m channels.run telegram`. Add `telegram_<chat_id>` to `config/user.yml` (im + permissions). All channels (Telegram, Discord, Slack, etc.) live under **channels/**; run any with `python -m channels.run <name>`.

---

## 7. References

- other agent repo: [https://github.com/other-agent/other-agent](https://github.com/other-agent/other-agent)
- other agent docs: [https://docs.other-agent.ai](https://docs.other-agent.ai) (gateway, agent, skills, tools, nodes, channels, security)
- Local clone used for this review: `../clawdbot`
- HomeClaw design: `Design.md` in this repo
- Minimal bot usage: `channels/webhook/README.md`
- Channels (Telegram, Discord, Slack, webhook): `channels/README.md`, `channels/telegram/README.md`

This Improvement.md can be updated as we implement items or refine priorities.
