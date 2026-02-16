# HomeClaw — design context and comparison

This document describes **HomeClaw** in the context of home-agent design (local vs cloud LLM, memory, tools, channels). Names and references may be updated over time.

---

## 1. Overview

| | HomeClaw | other agent |
|---|------------|----------|
| **Repo** | This repository | (other project) |
| **Tagline** | Local-first AI assistant; RAG + transcript memory; multi-channel (email, IM, CLI, webhook, WebSocket). | Personal AI assistant; multi-channel (WhatsApp, Telegram, Slack, Discord, etc.); tools and skills. |
| **Stack** | Python, FastAPI, SQLite, Chroma, llama.cpp, LiteLLM | Node/TypeScript, single Gateway (WS + HTTP), pi-mono–derived agent |
| **Primary LLM** | **Local** (llama.cpp) + optional cloud (LiteLLM) | **Cloud** (Anthropic/OpenAI) + optional local (e.g. Ollama) |
| **Control plane** | Core (FastAPI); channels are **separate** processes (or external bot code); Webhook/WebSocket also separate from Core | Single Gateway process (one port); **channel code runs inside** the Gateway or in extensions |

---

## 2. Side-by-Side Comparison

| Aspect | HomeClaw | other agent |
|--------|------------|----------|
| **Primary LLM** | Local (llama.cpp) + optional cloud (LiteLLM) | Cloud (Anthropic/OpenAI) + optional local (e.g. Ollama) |
| **Channels** | Email, Matrix, Tinode, WeChat, WhatsApp, CLI; **Webhook** (HTTP relay); **WebSocket** (/ws on Core); minimal **POST /inbound** for any bot | WhatsApp, Telegram, Slack, Discord, Google Chat, Signal, iMessage, BlueBubbles, Teams, Matrix, Zalo, WebChat, CLI |
| **Adding a new bot** | POST to Core `/inbound` or Webhook `/message` with `{ user_id, text }`; no new channel code. Channels (Telegram, Discord, Slack, etc.) in `channels/`. Example: `channels/telegram/` | Implement or enable a channel in the Gateway; bot tokens (Telegram, Discord, etc.) configured in gateway config |
| **Access from anywhere** | Yes (email/IM to home Core; or Webhook relay; or Tailscale/SSH + WebSocket) | Yes (channels + Tailscale/SSH for Control UI / WebChat) |
| **Control plane** | Core (FastAPI, HTTP + WebSocket); channels = separate processes or external bots calling /inbound | Single Gateway (WebSocket + HTTP on one port); channels run inside or connect to Gateway |
| **Memory** | **RAG** (SQLite + Chroma) + **session transcript** (JSONL, prune, summarize); embedding model for retrieval | Session transcripts (JSONL); workspace bootstrap files (AGENTS.md, SOUL.md, TOOLS.md) |
| **Extensibility** | Plugins (Python, description-based routing when orchestrator on); optional TAM (time intents) | Skills (SKILL.md, AgentSkills-compatible), plugins/extensions; ClawHub skill registry |
| **Agent capabilities** | Chat + RAG + optional plugin; **tool layer** (use_tools: true): exec, browser, cron, sessions_*, memory_*, file_*, etc. — most other agent-style tools | Chat + **tools**: exec, browser, canvas, nodes, cron, webhooks, sessions_* (agent-to-agent) |
| **Device control** | Not yet | **Nodes**: camera, screen, location, system.run/notify; exec on gateway or node; sandbox (Docker) for non-main |
| **Onboarding** | Manual config (YAML: core.yml, llm.yml, user.yml); CLI in main.py | Wizard (e.g. onboard, doctor) |
| **Remote exposure** | Channels/Core host:port; optional Webhook relay; no built-in tunnel (docs suggest Tailscale/SSH) | Tailscale Serve/Funnel, SSH tunnel; gateway auth (token/password) |
| **Multi-agent / sessions** | Single Core; user/session/run for chat and memory; user.yml allowlists | Multi-agent routing (workspace per agent); session model (main vs group, activation, queue) |
| **Config** | YAML (core.yml, llm.yml, user.yml, email_account.yml); channels/.env | JSON config; env vars; credentials in config directory |

---

## 3. Architecture (Simplified)

**HomeClaw**

```
Channels (Email, Matrix, WeChat, WhatsApp, CLI, Webhook, or any bot → /inbound)
    │
    ├── Full channel: HTTP PromptRequest → Core /process (async) or /local_chat (sync)
    └── Minimal: HTTP POST /inbound or WebSocket /ws → Core (sync)
                    │
                    ▼
    Core (FastAPI) → Permission → RAG + LLM → Reply (or route to Plugin)
                    │
                    ├── LLM: llama.cpp (local) or LiteLLM (cloud)
                    └── Memory: SQLite + Chroma + transcript
```

**other agent**

```
Channels (WhatsApp, Telegram, Slack, …) → Gateway (single process, one port)
                    │
                    ▼
    Gateway (WS + HTTP) → Pi agent (workspace, sessions) + Tools + Skills
                    │
                    ├── Tools: exec, browser, canvas, nodes, cron, …
                    └── Sessions (JSONL); bootstrap files (AGENTS.md, SOUL.md)
```

---

## 4. Similarities

- **Self-hosted personal assistant**: You run it on your own machine(s); data stays with you.
- **Multi-channel**: One assistant reachable from many surfaces (email, IM, CLI, etc.).
- **Access from anywhere**: Use from phone or elsewhere by talking through a channel (or, in other agent, via Tailscale/SSH + WebChat).
- **Central brain**: Single control plane (Core vs Gateway) that routes messages, checks permission, and generates replies.
- **Extensibility**: HomeClaw has plugins; other agent has skills and plugins.
- **Permission / allowlists**: Both restrict who can talk to the assistant (e.g. user.yml vs allowFrom / pairing).

---

## 5. Major Differences

| Dimension | HomeClaw | other agent |
|-----------|------------|----------|
| **LLM strategy** | **Local-first**: llama.cpp as default; cloud (LiteLLM) optional. Suited for privacy and offline. | **Cloud-first**: Anthropic/OpenAI recommended; local optional. Suited for best model quality and long context. |
| **Memory** | **RAG** (Chroma + SQLite) + **transcript** (session JSONL, prune, summarize); retrieval augments context. | **Transcript + bootstrap**: Session JSONL and workspace files (AGENTS.md, etc.); no vector RAG in core. |
| **Tools / actions** | **Tool layer** (use_tools: true): exec, browser, cron, sessions_*, memory_*, file_*, etc. — **most other agent-style tools**; model calls tools by name with args (function calling). **Plugins** (orchestrator) for Weather, News, etc. | **First-class tools**: exec, browser, canvas, nodes (camera, screen, location), cron, webhooks. Model **calls tools by name with args** (function calling); multiple tools per turn. |
| **Process model** | Core + **separate** channel processes (or external bots via /inbound); optional Webhook relay. | **Single** Gateway process; channels run inside or connect to it. |
| **Adding a bot** | **Minimal API**: Any bot can POST to `/inbound` (or Webhook); no new channel code in repo. | New channel implemented in codebase or as extension; bot token in config. |
| **Onboarding** | Manual YAML and CLI. | Wizard (e.g. onboard, doctor). |
| **Remote access** | Documented (Tailscale/SSH); no built-in tunnel or auth in Core. | Tailscale Serve/Funnel, SSH, gateway auth. |
| **Companion apps** | None yet (WebSocket /ws for future WebChat). | macOS app, iOS/Android nodes, Control UI. |

**Plugins vs other agent tools (short)**  
- **HomeClaw plugin**: “Route this message to one handler; handler does a thing and returns.” The model (orchestrator) picks a plugin from **descriptions**; no structured arguments. One plugin per turn.  
- **other agent tool**: The model gets **tool definitions** (name + parameters schema) and **calls** tools with JSON args (e.g. `exec` with `{"command": "ls"}`). Multiple tool calls per turn; results are fed back and the model can chain or reply.  
So: plugin = **intent routing + single handler**; tool = **function calling + execute + loop**. To get other agent-style “work” (exec, browser, nodes, etc.) in HomeClaw we need a **tool layer** (registry, schemas, tool-aware chat loop), not only plugins. See **Design.md §3.6** for the full comparison and the proposed design (tool registry, built-in tools, optional plugins-as-tools).

---

## 6. Summary

- **HomeClaw** focuses on **local LLM + RAG + transcript memory** and **simple deployment** (Python, SQLite, Chroma). Channels can be full (BaseChannel) or minimal (POST /inbound, WebSocket /ws, Webhook relay), so new bots can connect with little code.
- **other agent** focuses on **cloud AI + rich tools and skills** and a **single Gateway** with many built-in channels, onboarding wizard, and device nodes. Strong on “agent that can do things” (exec, browser, canvas, nodes).

Both are valid “home agent, accessible anywhere” designs; the choice depends on whether you prioritize **local LLM + RAG** (HomeClaw) or **powerful tools + polished ops** (other agent).

---

## 7. Memory in Detail (and What We Can Learn from other agent)

This section explains how each project handles memory and context, and analyzes the design difference: **conversation-centric** (HomeClaw, like ChatGPT) vs **action-centric** (other agent, “do real things”). The goal is to learn from other agent while keeping our own strengths.

### 7.1 HomeClaw memory (RAG: SQLite + Chroma; transcript: JSONL, prune, summarize)

**What we have**

- **SQLite** (via SQLAlchemy + `memory/storage.py`, `memory/database/`):
  - **Chat history**: `homeclaw_chat_history` — per turn: `app_id`, `user_id`, `session_id`, `question`, `answer`, `metadata`, `created_at`. Used to load the last N turns (e.g. 6) into the prompt as recent conversation.
  - **Sessions**: `homeclaw_session_history` — session metadata per app/user/session.
  - **Runs**: `homeclaw_run_history` — run metadata per agent/user/run.
  - **Memory change history**: `memory/storage.py` — history table for memory CRUD events (old/new value, event type) for audit/debug.
- **Chroma** (vector store in `memory/chroma.py`):
  - Stores **embedded snippets** of past user/assistant content (and optional deduced “memories”). Each record has vector + payload (`data`, `user_id`, `session_id`, `run_id`, etc.).
  - Used for **semantic retrieval**: given the current query (and optional filters), we search for the top‑k similar vectors and inject that text as “relevant memories” into the system/context.
- **Embedding model**: Same config as `embedding_llm` (local llama.cpp or cloud). Used to embed text before storing in Chroma and to embed the query for search.
- **Flow**:
  1. Incoming user message → permission check → load **recent chat** from SQLite (last 6 turns) → optionally enqueue to **memory_queue**.
  2. Background worker: `process_memory_queue()` takes the request and calls `mem_instance.add(...)` → embed text → insert into Chroma (and optional SQLite history).
  3. When generating a reply: `answer_from_memory()` → `_fetch_relevant_memories(query, …)` runs **vector search** in Chroma (by query, scoped by user_id/session_id/run_id etc.) → builds a “memories” string → injects it into the **system prompt** (e.g. “Background information: …”) → then **LLM** (main_llm) with **recent chat + current query** → response saved to **chat history** (SQLite).
- **Function calling**: Used for chat/completion (and for plugin routing when orchestrator is on). No built-in exec or device tools; plugins (Weather, News, etc.) are feature-specific.

- **Session transcript** (first-class; Design §3.4): Chat history exposed as **session transcript** per (app_id, user, session_id) — list or **JSONL**; optional **prune** (keep last N turns) and **summarize** (LLM summary). APIs: `get_transcript`, `get_transcript_jsonl`, `prune_session`, `summarize_session_transcript`.

**Summary**: **Chat-first + RAG + transcript.** Context = recent conversation (SQLite) + retrieved “memories” (Chroma). We also support **session transcript** (JSONL, prune, summarize) like other agent. Good for **ongoing conversation** and **personal context** (preferences, past facts). Like ChatGPT with optional transcript export/prune/summary.

---

### 7.2 other agent memory (transcript + workspace bootstrap)

**What other agent uses**

- **Session transcript** (conversation log per session):
  - Stored as **transcript logs** per session; exposed via tools like `sessions_history` (fetch transcript for a session).
  - Typically a **linear, chronological log** of the conversation (often JSONL or equivalent): who said what, when. Used as the **in-session context** for the agent (recent turns or full transcript depending on pruning/summarization).
  - **No vector store in core**: context is **transcript + injected files**, not semantic search over a separate RAG store.
- **Workspace bootstrap files** (loaded at session/agent start):
  - **AGENTS.md**: Defines **agent behavior and routing** (multi-agent, which agent handles what, isolation). Part of the template system; see [Templates: AGENTS]((external docs)reference/templates/AGENTS).
  - **SOUL.md**: Defines **identity and personality** — who the agent is, voice, worldview, thinking style. Can be built from interviews or existing content; loaded at session start and shapes all behavior. Can be extended (e.g. SOUL_EVIL.md for persona switching). See [Templates: SOUL]((external docs)reference/templates/SOUL).
  - **TOOLS.md**: Describes **tools** the agent can use (exec, browser, canvas, nodes, cron, webhooks, sessions_*). Injected so the model knows what it *can* do. See [Templates: TOOLS]((external docs)reference/templates/TOOLS).
  - Workspace root: e.g. `(config dir)/workspace`; skills live under `workspace/skills/<name>/SKILL.md`.
- **Session model**: Main vs group, activation (e.g. mention), queue, reply-back. Enables multi-agent routing and “which conversation” the message belongs to.
- **Tools that “do real things”**: exec, browser, canvas, nodes (camera, screen, location), cron, webhooks, `sessions_list` / `sessions_history` / `sessions_send`. Memory is in service of **actions**: identity (SOUL) + tools (TOOLS) + transcript (what happened so far).

**Summary**: **Action-first + identity.** Context = **session transcript** (what was said in this thread) + **workspace bootstrap** (who the agent is, what it can do). No RAG over a separate vector store; the “memory” that matters for the next step is the **conversation so far** and the **fixed identity/tool definitions**. Designed so the agent can **execute**, **browse**, **control devices**, and **coordinate sessions**, not just chat.

---

### 7.3 Analysis: conversation-centric vs action-centric

| Dimension | HomeClaw (ChatGPT-style) | other agent |
|-----------|----------------------------|----------|
| **Primary use** | **Conversation**: answer questions, follow up, personalize over time. | **Do things**: run commands, use browser/canvas, talk to devices and other sessions. |
| **Context source** | Recent **chat** (SQLite) + **vector RAG** (Chroma) over past content; **session transcript** (list/JSONL, prune, summarize). | **Transcript** (linear log of session) + **bootstrap files** (AGENTS, SOUL, TOOLS). |
| **“Memory”** | Durable **semantic** memory (Chroma) + **conversation** memory (SQLite) + **transcript** (JSONL, prune, summarize). | **Session-scoped** transcript + **identity/capabilities** in markdown. |
| **Function calling** | Used for **chat** (and plugin routing). | Used for **tools**: exec, browser, nodes, cron, sessions_*, etc. |
| **Strength** | Good at **long-term personal context** and **recall** (“remember when I said…”) via RAG. | Good at **task execution** and **multi-session** coordination; clear **identity** and **tool surface**. |

- **HomeClaw**: Like ChatGPT — SQLite + vector store; embedding model for retrieval; focus on **chat** and **recall**. Plugins add features but there is no first-class exec/device layer.
- **other agent**: Designed so the agent **does real things**; memory is **transcript + workspace files**. No vector RAG; context is “this session’s log + who I am + what I can do.”

---

### 7.4 What we can adopt from other agent (and keep our own)

**Keep (our strengths)**

- **RAG (SQLite + Chroma)** and **embedding-based retrieval** for long-term, semantic “remember this” across sessions.
- **Chat history in SQLite** (sessions, runs, chat turns) as the source of truth for conversation.
- **Local-first LLM** and **simple stack** (Python, FastAPI, no Node Gateway).

**Adopt or adapt (from other agent)**

1. **Workspace bootstrap files (optional)**  
   - Introduce a **workspace** dir (e.g. `config/workspace/` or `~/.homeclaw/workspace/`) with optional markdown files:
     - **AGENTS.md** (or our equivalent): high-level agent behavior / routing hints (even if we stay single-Core for now).
     - **SOUL.md** (or **IDENTITY.md**): **identity and tone** — who the assistant is, how it should respond. Injected into the system prompt at session start or per request. Complements our RAG: RAG = *what* to remember; SOUL = *who* the agent is.
     - **TOOLS.md**: **Human-readable list of tools** (plugins + any future tools). Injected so the model knows what it can do; aligns with other agent’s “tools first” idea without requiring exec/nodes.
   - Implementation: load these files at startup or when building the system prompt; append (or optionally replace) a section of the system prompt. Keeps our flow; adds clarity and identity.

2. **Session transcript as a first-class artifact**  
   - We already have **chat history** in SQLite; we can expose it as a **session transcript** (e.g. JSONL or a simple list of `{ role, content, timestamp }`) per `(user_id, session_id)`.
   - Use for: debugging, export, or (later) feeding a “recent transcript” block into the prompt in a structured way (like other agent’s transcript). Optionally **session pruning/summarization** (e.g. summarize old turns, keep last N + summary) to avoid context overflow.

3. **Clear separation: “conversation memory” vs “identity/capabilities”**  
   - **Conversation memory**: Our RAG + chat history (what was said, what to recall).  
   - **Identity/capabilities**: Bootstrap files (who the agent is, what tools/plugins exist).  
   This matches other agent’s split (transcript vs AGENTS/SOUL/TOOLS) while keeping our RAG.

**Not adopting (by choice)**

- We do **not** add exec/browser/nodes/cron in core by default; that’s other agent’s domain. We can later add a **safe exec** or **tool runner** plugin if we want “do real things” without merging architectures.
- We keep **Core + separate channels** and **minimal /inbound API**; we don’t merge into a single Node Gateway.

---

### 7.5 Short summary

- **HomeClaw memory**: **RAG** (SQLite for chat/sessions/runs + Chroma for vector retrieval) + **session transcript** (JSONL, prune, summarize); **conversation-centric**; function calling for chat and plugin routing.
- **other agent memory**: **Session transcript** (JSONL-like) + **workspace bootstrap** (AGENTS.md, SOUL.md, TOOLS.md); **action-centric**; tools for exec, browser, nodes, sessions.
- **Takeaway**: We keep **RAG and chat history**; we can add **workspace bootstrap files** (identity + tools description) and **session transcript** as first-class concepts to move slightly toward “do real things” and clearer identity, without dropping what already works.

---

### 7.6 Prompt engineering + memory: direct comparison, “which is better?”, and potential problems

This subsection compares **prompt engineering** (workspace/bootstrap) and **memory** (context the model sees) between HomeClaw and other agent, when each is better, and what can go wrong.

#### Prompt engineering (workspace / bootstrap)

| Aspect | HomeClaw (after §7.4) | other agent |
|--------|--------------------------|----------|
| **What** | `config/workspace/`: IDENTITY.md, AGENTS.md, TOOLS.md. Injected into system prompt per request. | `(config dir)/workspace/`: AGENTS.md, SOUL.md, TOOLS.md (and SKILL.md per skill). Injected at session start / bootstrap. |
| **Role** | Identity (who), agents (behavior/routing), tools (capabilities). Same idea as other agent’s SOUL/AGENTS/TOOLS. | SOUL = identity/personality; AGENTS = routing/behavior; TOOLS = tool descriptions. |
| **When loaded** | Every reply in `answer_from_memory()` (read from disk each time unless you add caching). | Typically at session/agent start (bootstrap); transcript is the changing part. |
| **Better when** | You want identity + capabilities in the same process as RAG and chat, with one codebase. | You want a single bootstrap at session start and long-lived sessions with transcript as the only changing context. |

**Verdict (prompt engineering):** Conceptually the same (identity + behavior + tools in markdown). HomeClaw now has the same *kind* of prompt engineering as other agent; other agent has more mature templates and session-scoped bootstrap. Neither is strictly “better”; they fit different process models (per-request load vs session bootstrap).

#### Memory (what context the model gets)

| Aspect | HomeClaw | other agent |
|--------|------------|----------|
| **Conversation** | **Chat** (SQLite): last N turns loaded into `messages`. **Session transcript** (get_transcript, get_transcript_jsonl, prune_session_transcript, summarize_session_transcript) for export, prune, summarize. | **Transcript** (e.g. JSONL) per session; linear log. May be pruned/summarized. No vector store. |
| **Long-term / recall** | **RAG** (Chroma): embed query → vector search → inject “relevant memories” into system prompt. Cross-session, semantic. | **None in core.** Context = transcript (this session) + bootstrap. Long-term “memory” would be custom (e.g. external store or future feature). |
| **Better when** | You need “remember what I said / what we discussed” across sessions and semantic search (“things like X”). | You need “this session only” context and minimal infra; actions (exec, browser, nodes) are the focus, not recall. |

**Verdict (memory):** HomeClaw is **better for long-term, semantic recall** (RAG + chat). other agent is **better for session-scoped, action-oriented** context (transcript + tools). “Better” depends on whether you prioritize **recall across sessions** (HomeClaw) or **session + tools** (other agent).

#### Which is “better” overall?

- **For conversation + recall (“remember me”, “what did we say about X”)**: HomeClaw (RAG + chat + workspace) is stronger.
- **For doing things (exec, browser, devices, multi-session coordination)**: other agent (transcript + bootstrap + tools) is stronger.
- **For prompt engineering alone**: Roughly even after §7.4; both use markdown for identity/agents/tools. other agent has a richer template/session story; HomeClaw has simpler per-request injection.

So: **better at what?** HomeClaw = recall + personal context; other agent = actions + session context.

#### Potential problems

**HomeClaw (prompt engineering + memory)**

- **Workspace**: Loading from disk on every request can add latency and I/O; no caching by default. **Mitigation**: Cache workspace content in memory (e.g. at startup or with TTL) if needed.
- **Workspace + RAG in one system message**: Long identity/agents/tools + long RAG context can use a lot of tokens and dilute the model’s focus. **Mitigation**: Keep workspace files short; limit RAG top-k and total context length.
- **RAG quality**: Retrieval depends on embedding model and chunking. Bad embeddings or too few/too many chunks → irrelevant or missing memories. **Mitigation**: Tune embedding model, chunk size, and filters (user_id, session_id).
- **Chat window**: Only last N turns (e.g. 6) in prompt; long conversations lose older context unless RAG brings it back. **Mitigation**: RAG compensates; optional `summarize_session_transcript` and `prune_session_transcript` for very long sessions.

**other agent (prompt engineering + memory)**

- **No vector RAG**: Can’t do semantic “find past mentions of X” across sessions. **Mitigation**: Rely on transcript for this session; long-term recall would need an external or custom solution.
- **Transcript length**: Long sessions → huge context; risk of hitting context limits or high cost. **Mitigation**: Pruning, summarization, or “recent + summary” (other agent has session pruning concepts).
- **Bootstrap at session start**: If SOUL/AGENTS/TOOLS change mid-session, the agent may not see updates until next session. **Mitigation**: Restart session or support “reload bootstrap” if needed.
- **Identity in markdown only**: SOUL/TOOLS are prompt text; the model can still ignore or override them. **Mitigation**: Clear wording, testing, and (if needed) guardrails or tool-use constraints outside the prompt.

**Common / both**

- **Prompt injection**: User (or channel) content can try to override instructions. Both rely on system prompt + separation of user message. **Mitigation**: Sanitize/limit user input where critical; consider future guardrails.
- **Token limits**: Long system prompt (workspace + RAG or bootstrap + long transcript) can exceed model context. **Mitigation**: Cap lengths, summarize, or prioritize (e.g. identity short, RAG/transcript bounded).

---

### 7.7 One-paragraph summary (prompt engineering vs memory)

**HomeClaw** now has **prompt engineering** (workspace: IDENTITY, AGENTS, TOOLS) similar to other agent’s bootstrap, plus **memory** = RAG (Chroma) + chat (SQLite) + **transcript** (JSONL, prune, summarize). So we get both “who the agent is” (workspace) and “what was said / what to recall” (memory). **other agent** has **prompt engineering** (AGENTS, SOUL, TOOLS) and **memory** = session transcript only (no vector RAG). So: **which is better?** — HomeClaw for **recall and personal context**; other agent for **session + actions**. **Potential problems** — HomeClaw: workspace + RAG length, RAG quality. other agent: no cross-session semantic recall, transcript length, bootstrap fixed at session start. Both: prompt injection risk, token limits.

---

### 7.8 Memory: comparison and summary

| | HomeClaw | other agent |
|---|------------|----------|
| **What counts as “memory”** | **Conversation**: SQLite chat (last N turns in prompt). **Long-term**: Chroma vector store (embed → search → inject “relevant memories”). **Transcript**: Session transcript (list/JSONL, prune, summarize) per session. | **Conversation**: Session transcript (e.g. JSONL); linear log of this session. **Identity/capabilities**: Workspace bootstrap (AGENTS, SOUL, TOOLS) loaded at session start — not “recall” but fixed context. |
| **Storage** | SQLite (chat, sessions, runs) + Chroma (vectors). | Transcript per session (file/DB); no vector store in core. |
| **Retrieval** | Embedding model → vector search (Chroma) → top‑k snippets into system prompt. | No semantic retrieval; context = full/recent transcript + bootstrap. |
| **Scope** | **Cross-session**: RAG can recall “what we said about X” across users/sessions. Chat window = current session’s last N turns. | **Per-session**: Transcript is this session only. No built-in “remember across sessions.” |
| **Pruning / summarization** | Optional: `prune_session_transcript`, `summarize_session_transcript` (Design §3.4). RAG naturally limits by top‑k. | Transcript may be pruned/summarized to control context size. |
| **Strength** | **Recall**: “Remember when I said…”, “what did we discuss about X?” — semantic search over past content. | **Session focus**: Clear “this conversation” context; simple; good for action loops (exec, browser, nodes) where identity + transcript matter. |
| **Weakness** | RAG quality and length; workspace + RAG can bloat system prompt. | No cross-session semantic memory; long sessions need pruning/summary. |

**Summary**

- **HomeClaw memory** = **chat (SQLite)** + **RAG (Chroma)** + **transcript** (JSONL, prune, summarize). Conversation-centric: recent turns in the prompt plus *retrieved* past content; session transcript available for export/prune/summary like other agent. Best when you want **long-term, semantic recall** (“remember me”, “things like X”) across sessions.
- **other agent memory** = **session transcript** + **bootstrap (AGENTS, SOUL, TOOLS)**. Action-centric: “what was said in this thread” plus “who I am and what I can do.” Best when you want **this-session context** and **tools/identity** without a vector store.
- **Choose HomeClaw** if recall and personal context across time matter more; **choose other agent** if session-scoped context and action-oriented tools matter more. For **how memory is used** in each system and **how to use RAG and transcript together** in HomeClaw, see §7.9.

---

### 7.9 How memory is used: difference, and using RAG + transcript in HomeClaw

This subsection clarifies **how** each system uses memory (not just what they store), and gives practical guidance for using **both** RAG and transcript in HomeClaw.

#### Difference: how each system uses memory

**other agent: transcript in service of “dedicated work”**

- **What it has**: Session transcript (e.g. JSONL) + workspace bootstrap (AGENTS, SOUL, TOOLS). No vector RAG.
- **How memory is used**: The **transcript** is the only conversation context the model gets for “what happened in this session.” It is fed (possibly pruned or summarized) so the agent knows the recent dialogue when deciding the **next action** — exec, browser, canvas, nodes, `sessions_send`, etc. The **bootstrap** tells the agent who it is and what tools it can use. So memory is used to support **doing things in this thread**: “given what we just said, run this command,” “given this conversation, send that to another session.” Long-term recall (“remember what we said last week”) is **not** in scope; the design is **this session, these actions**. Transcript is there to support that dedicated work.

**HomeClaw: RAG for chatting, transcript as artifact + hygiene**

- **What it has**: RAG (SQLite + Chroma) + chat (last N turns) + session transcript (list/JSONL, prune, summarize).
- **How memory is used today**:
  1. **Chat (SQLite)**: The last N turns (e.g. 6) are **always** loaded into the prompt as the recent conversation. This is the primary “this session so far” context for generating the reply.
  2. **RAG (Chroma)**: The current user message (and optionally filters) is used to **query** the vector store; top‑k similar snippets are retrieved and injected into the system prompt as “relevant memories.” So the model gets **semantic recall** across sessions — “remember when I said…”, “what did we discuss about X?”
  3. **Transcript**: Today the transcript is **not** automatically injected into the prompt. It is a **first-class artifact**: you can get it (list or JSONL), prune it (keep last N turns), or summarize it (LLM summary). So transcript is used for **export, debugging, hygiene, and future use** (e.g. feeding a “recent transcript” or “summary + recent” block into the prompt).

So the **difference**: other agent uses **only** transcript (plus bootstrap) to drive **action** in the current session. HomeClaw uses **RAG + recent chat** to drive **conversation and recall**; transcript is the same underlying data (chat history) exposed for **session-level** use (export, prune, summarize, and optionally context later).

#### HomeClaw: how to use RAG and transcript together

Because HomeClaw has **both** RAG and transcript, it helps to be explicit about when to use which.

| Use case | Use this | Why |
|----------|----------|-----|
| **Replying to the user with recall** | **RAG + last N turns** | RAG gives cross-session “memories”; last N turns give recent dialogue. This is the current default in `answer_from_memory()`. |
| **“Remember what I said / what we discussed”** | **RAG** | Semantic search over Chroma; no need for full transcript. |
| **Export or audit a session** | **Transcript** (`get_transcript`, `get_transcript_jsonl`) | Linear log per session; JSONL for external tools or logs. |
| **Cap session size (avoid huge history)** | **Transcript** (`prune_session_transcript`) | Keep only the last N turns for that session; delete older ones. |
| **Short summary of a long session** | **Transcript** (`summarize_session_transcript`) | LLM summarizes the transcript; use for display, or (later) inject “summary + last N turns” into the prompt. |
| **Future: “session summary + recent” in prompt** | **Transcript** (summarize + last N) | Like other agent: inject a summary of older turns plus the last few turns as explicit context. Not wired in by default yet; transcript APIs support building this. |

**Summary**

- **RAG** = main **conversation memory** for HomeClaw: recall across sessions, used every reply.
- **Transcript** = **session artifact**: same data as chat history, but exposed per session for **export, prune, summarize**, and (optionally) for feeding a “recent transcript” or “summary + recent” block into the prompt later. So: use **RAG for chatting and recall**; use **transcript for session-level ops and for future richer session context** if you add it.
- **other agent** uses transcript **only** because its job is “do things in this session”; no RAG. **HomeClaw** uses RAG for that “remember me” job and keeps transcript for session-level control and compatibility with other agent-style workflows (export, prune, summarize).

#### So can HomeClaw “chat as before” and “work as other agent”?

- **Chat as before**: **Yes.** RAG + last N turns drive the reply; recall across sessions works as before. Nothing changed for normal chatting.
- **Memory/context like other agent**: **Yes.** We have **session transcript** (JSONL, prune, summarize) and **workspace bootstrap** (IDENTITY, AGENTS, TOOLS). So we have the same *kind* of context: identity + session artifact. You can export, prune, and summarize transcripts like other agent.
- **“Work” as other agent (do the same actions)**: **Mostly yes.** other agent’s “work” is **first-class tools**: exec, browser, canvas, nodes (camera, screen, location), cron, webhooks, sessions_*. HomeClaw now implements **most of these** in its tool layer (use_tools: true): exec (with background), process_*, file_*, folder_list, fetch_url, web_search, browser_*, cron_*, sessions_list/transcript/send/**spawn**/session_status, memory_search/get, time, models_list, agents_list, image, webhook_trigger, etc. **Out of scope** (no equivalent): canvas, nodes (device control), gateway admin, channel-specific “message” send. So we can **chat** as before (RAG + recall), use **memory/context** like other agent (transcript + workspace), and **do** exec, browser, cron, and multi-session actions (including sessions_spawn) the way other agent does — except device nodes and canvas.

**Short answer**: HomeClaw can **chat as before** (RAG + recall), has **the same style of memory/context** as other agent (transcript + workspace), and **most other agent tools are now implemented** (exec, browser, cron, sessions_*, memory_*, file_*, etc.). Not implemented: canvas, nodes (device control), gateway admin.

---

### 7.9.1 other agent: tools vs skills (in detail)

Your understanding is right: **tools** are other agent’s capabilities; **skills** are description-based “agents” (instruction packages) that teach the agent how to use those tools to do things. In other words: **tools = static base** (the callable API); **skills = the application layer**—there can be many (ClawHub has thousands), each using different tools to finish different tasks.

#### Tools = capabilities

- **What they are**: Built-in **actions** the agent can perform. Each tool has a **name** and a **parameters schema**; the model uses **function calling** to invoke them with JSON arguments.
- **Examples**: `exec` (run shell commands), `browser` (navigate, snapshot, click, type), `nodes` (camera, screen, location, system.run), `cron` (schedule recurring tasks), webhooks, `sessions_list` / `sessions_send` (agent-to-agent), etc.
- **How they’re used**: The Gateway injects **tool definitions** into the prompt (often summarized in TOOLS.md). When the user says “run ls” or “open example.com and click the button,” the model outputs **tool_calls** (tool name + args); the Gateway executes the tool and returns the result; the model can chain more tool calls or reply with text.
- **Summary**: Tools = *what the agent can do* (the API surface). No “personality” or task strategy—just callable functions.

#### Skills = description-based “agents” that use tools

- **What they are**: [AgentSkills](https://agentskills.io)-compatible **skill folders**. Each skill is a directory with a **SKILL.md** file: **YAML frontmatter** (`name`, `description`) + **markdown body** (instructions, steps, when to use which tool). Optionally: `scripts/`, `references/`, `assets/`.
- **Role**: other agent’s docs say skills **“teach the agent how to use tools.”** So:
  - **TOOLS.md** (or the injected tool list) = “here are the tools you *can* call.”
  - **Skills** = “here is *how* to use them for this kind of task” — strategy, workflow, when to use browser vs exec vs cron, etc.
- **Examples**: A “social-media-agent” skill might describe: use `browser` to open Twitter, use `cron` to post at 9am daily, use `sessions_send` to hand off to another agent. The model doesn’t “become” a different agent; it gets **extra instructions** (the skill’s description + body) so it knows *how* to combine tools for that task.
- **Loading**: Skills are loaded from workspace `skills/`, `(config dir)/skills`, and bundled skills. At session start (or when the skills list is built), other agent injects an **“Available skills”** list (name + description, and optionally full body) into the system prompt. The model then *knows* about those skills and can “apply” them by following the instructions while calling tools.
- **Summary**: Skills = *task/role descriptions + instructions* that tell the agent how to use tools for specific goals. They don’t add new tools; they add **know-how** (when and how to use existing tools).

#### Relationship

| | Tools | Skills |
|---|--------|--------|
| **What** | Callable actions (exec, browser, cron, …) with name + parameters. | Instruction packages (SKILL.md: name, description, body) that describe *how* to use tools. |
| **Injected as** | Tool definitions (function-calling schema) + often TOOLS.md summary. | “Available skills” list (name + description, optionally full body) in the system prompt. |
| **Model uses** | Outputs `tool_calls` with name + JSON args; Gateway runs the code. | Reads instructions; decides when a skill applies; follows the skill’s steps *by calling tools*. |
| **Adds** | *Capabilities* (what the agent can do). | *Know-how* (how to do a certain task with those capabilities). |

So: **tools = capabilities; skills = description-based agents that use those tools to do things.** Skills don’t implement new tools; they guide the same LLM + same tools toward specific workflows (e.g. “post daily at 9am” or “draft a tweet and open the composer”).

---

### 7.10 Reusing other agent skills and tools in HomeClaw

**Short answer**: **Tools** — not direct reuse (different runtime); HomeClaw has its own Python tools with the same *capabilities*. **Skills** — yes, the **format** can be reused: load SKILL.md (and optionally scripts) so HomeClaw can use ClawHub-style skills.

**Which skills to use:** HomeClaw should **utilize all other agent/ClawHub skills** that do *not* rely on **canvas, nodes, or gateway**. Those three tools are **not used frequently** in skills; most skills use exec, browser, cron, sessions_*, memory, file, web—all of which HomeClaw has. So the vast majority of other agent skills are usable in HomeClaw.

#### other agent tools (exec, browser, nodes, etc.)

- other agent’s tools are **built into the Node/TypeScript Gateway**. They are not a separate library we can call from Python.
- **Direct reuse**: Not possible — different language and process.
- **Capability reuse**: HomeClaw already implements **equivalent tools** in Python: exec, fetch_url, browser_navigate, folder_list, file_read, webhook_trigger, sessions_transcript, sessions_list, time, env, cwd, etc. So we get the same *kinds* of actions, not the same code.
- **Summary**: Use HomeClaw’s tool layer for “tools”; no need to run other agent’s Gateway for tool execution.

#### other agent skills (SKILL.md, ClawHub)

- **What they are**: A skill is a folder with a **SKILL.md** file (YAML frontmatter: `name`, `description`; optional: `homepage`, `user-invocable`, `disable-model-invocation`, `metadata`) plus a markdown body (instructions). Optionally: `scripts/` (Python, Bash, etc.), `references/`, `assets/`. ClawHub is the public registry (3,000+ skills); install with `clawhub install <slug>` into a workspace `skills/` directory.
- **Reuse in HomeClaw — possible in two ways:**

| Approach | What it means | Effort |
|----------|----------------|--------|
| **1. Format reuse** | Add a **skill loader** in HomeClaw that reads **SKILL.md** (from a local folder or from unpacked ClawHub bundles). Parse YAML frontmatter + body; inject each skill’s name and description (and optionally full body) into the system prompt or a “Skills” block. The model then *knows* about those skills and can describe or “use” them in conversation. No execution of scripts yet. | Small: one loader module, scan a `config/skills/` or `workspace/skills/` dir. |
| **2. Catalog + script execution** | Same as (1), plus: if a skill has a `scripts/` folder, expose a tool (e.g. **run_skill**) that runs a script from that skill with arguments. Conventions (how other agent passes args to scripts) would need to be documented or discovered; we could start with “run script by path under skills dir” with an allowlist. | Medium: loader + one tool that runs scripts under a skills root with safety checks. |

- **Practical steps**  
  - **Today**: You can **manually** copy skill folders from ClawHub (or after `clawhub install X` in an other agent workspace) into a directory that HomeClaw reads (e.g. `config/skills/`), and add a loader that parses SKILL.md and appends “Available skills: …” to the system prompt. That gives **format and catalog reuse** without running other agent.  
  - **Later**: Add a **run_skill** tool that executes a script from a loaded skill (with a strict allowlist and sandbox) so script-based skills can be reused in behavior, not only in description.

#### 7.10.1 other agent tool inventory and HomeClaw parity

other agent exposes the following **first-class agent tools** (from external docs). HomeClaw aims to implement equivalent capabilities where feasible (same process, no extra hardware).

| other agent tool | Description | HomeClaw | Notes |
|---------------|-------------|-----------|--------|
| **group:runtime** | | | |
| `exec` | Run shell commands (command, timeout, background) | **exec** | Allowlist in config; **background** param for background run → job_id. |
| `bash` | Shell variant | Same as exec | Use **exec**. |
| `process` | Manage background exec sessions (list, poll, log, kill) | **process_list**, **process_poll**, **process_kill** | In-memory job store; exec(background=true) returns job_id. |
| **group:fs** | | | |
| `read` | Read file | **file_read** | Path under `tools.file_read_base`. |
| `write` | Write file | **file_write** | Same base path. |
| `edit` / `apply_patch` | Edit file (patch/hunk) | **file_edit**, **apply_patch** | file_edit: old_string/new_string; apply_patch: unified diff. |
| **group:web** | | | |
| `web_search` | Search the web (e.g. Brave API) | **web_search** | Optional; requires `BRAVE_API_KEY` or config. |
| `web_fetch` | Fetch URL, extract content | **fetch_url** | Lightweight; **browser_navigate** for JS-heavy. |
| **group:ui** | | | |
| `browser` | Navigate, snapshot, act (click/type), screenshot | **browser_navigate**, **browser_snapshot**, **browser_click**, **browser_type** | Playwright; one session per request. |
| `canvas` | Node Canvas (A2UI, present, snapshot) | Out of scope | Requires other agent nodes/device. |
| **group:automation** | | | |
| `cron` | Add, list, update, remove, run cron jobs | **cron_schedule**, **cron_list**, **cron_remove** | TAM + croniter. |
| `gateway` | Restart gateway, config | Out of scope | Admin; single Core, no gateway process. |
| **group:sessions** | | | |
| `sessions_list` | List sessions | **sessions_list** | ✓ |
| `sessions_history` | Transcript for a session | **sessions_transcript** | ✓ |
| `sessions_send` | Send message to another session | **sessions_send** | Core.send_message_to_session; target by session_id or (app_id, user_id); returns target's reply. |
| `sessions_spawn` | Spawn sub-agent run | **sessions_spawn** | Sub-agent one-off run; optional **llm_name** (ref) or **capability** (e.g. Chat) to select model; **models_list** for refs + capabilities. |
| `session_status` | Current session info | **session_status** | Returns session_id, app_id, user, etc. |
| **group:memory** | | | |
| `memory_search` | Search stored memories | **memory_search** | Uses Core RAG (Chroma); when `use_memory` is on. |
| `memory_get` | Get memory by id | **memory_get** | Core.get_memory_by_id; when use_memory is on. |
| **group:nodes** | | | |
| `nodes` | Paired devices: notify, run, camera, screen, location | Out of scope | Requires other agent nodes (iOS/Android/macOS app). |
| **Other** | | | |
| `image` | Analyze image (vision model) | **image** | path or url + prompt; Core.analyze_image; requires vision-capable LLM (multimodal). |
| `message` | Send to Discord/Slack/Telegram/etc. | **channel_send** | Send additional message(s) to the **last-used channel** (send_response_to_latest_channel). No multi-channel-at-once; simple “same channel” logic. |
| `agents_list` | List agent ids (for sessions_spawn) | **agents_list** | Returns single-agent note in HomeClaw. |
| (models_list) | List models + capabilities (for llm/capability selection) | **models_list** | Returns refs + model_details (ref, alias, capabilities); use for sessions_spawn llm_name or capability. |

**Summary**: **Most other agent tools are now implemented in HomeClaw.** Implemented: **exec** (with **background**), **process_list**/**process_poll**/**process_kill**, **file_read**/**file_write**/**file_edit**/**apply_patch**, **folder_list**, **fetch_url**/**web_search**, **browser_***, **webhook_trigger**, **cron_schedule**/**cron_list**/**cron_remove**, **sessions_list**/**sessions_transcript**/**sessions_send**/**sessions_spawn**/**session_status**, **memory_search**/**memory_get**, **time**, **env**, **cwd**, **platform_info**, **echo**, **agents_list**, **models_list** (refs + capabilities for llm/capability selection), **image** (vision/multimodal), **channel_send** (send additional message(s) to last-used channel). **Out of scope**: canvas, nodes, gateway.

#### 7.10.2 Canvas, nodes, gateway, message: what they are and why HomeClaw does or doesn’t implement them

Review of the four “out of scope” items: what each is in other agent, whether HomeClaw can or should implement it, and why.

---

**1. Canvas**

| What it is (other agent) | Why HomeClaw doesn’t have it / is it necessary? |
|-----------------------|---------------------------------------------------|
| **Canvas** is a **node tool**: the agent drives a **visual panel** on a **paired device** (macOS/iOS/Android companion app). Actions: `present`, `hide`, `navigate`, `eval`, `snapshot`, and **A2UI** (push UI surfaces in v0.8 JSONL). The panel is a WKWebView in the other agent macOS app (or equivalent on iOS/Android); the Gateway calls `node.invoke` (e.g. `canvas.present`, `canvas.snapshot`) over the node WebSocket. So: “show this URL or A2UI on the user’s device.” | **Requires other agent nodes**: Canvas is part of the **node** protocol. You need a **companion app** (other agent macOS/iOS/Android) that connects to the Gateway as a node and exposes `canvas.*` commands. HomeClaw has **no node protocol and no companion app**. **Implementing it** would mean: (a) defining a node-like protocol (WebSocket + command surface), (b) building or adopting a companion app that hosts a Canvas-like WebView and responds to present/navigate/snapshot/A2UI. That’s a large, other agent-specific stack. **Necessary?** Only if you want “agent shows a panel on the user’s phone/desktop” from within HomeClaw; for many use cases (chat, exec, browser on server, sessions) it’s **not necessary**. **Verdict**: **Cannot implement** without a node stack + companion app; **not necessary** unless you explicitly want device Canvas. |

---

**2. Nodes**

| What it is (other agent) | Why HomeClaw doesn’t have it / is it necessary? |
|-----------------------|---------------------------------------------------|
| **Nodes** are **companion devices** (macOS/iOS/Android or headless host) that connect to the Gateway over **WebSocket** (`role: node`) and expose a command surface via `node.invoke`. The agent uses the **nodes** tool to: **pairing** (status, describe, pending/approve/reject), **notify** (e.g. macOS `system.notify`), **run** (e.g. `system.run` on the node host), **camera_snap** / **camera_clip**, **screen_record**, **location_get**, and **Canvas** (see above). So: “run a command on that Mac,” “take a photo on that phone,” “get location,” “show Canvas on that device.” | **Requires other agent’s node ecosystem**: (1) A **Gateway** that speaks the node WebSocket protocol and keeps pairing/device state. (2) **Companion apps** (or headless `node run`) that connect as nodes and implement `system.*`, `camera.*`, `screen.*`, `location.*`, `canvas.*`. HomeClaw has a **Core**, not a Gateway; it has **no node protocol, no pairing store, no companion apps**. **Implementing it** would mean: node protocol, pairing/approval flow, and either shipping companion apps or telling users “run an other agent node and point it at Core” (and extending Core to speak the node protocol). **Necessary?** Only if you want “agent controls my phone/other Mac” (camera, screen, location, run, notify). For server-side automation (exec on Core host, browser on Core host), **not necessary**. **Verdict**: **Cannot implement** without a full node stack and devices; **not necessary** unless you need device control (camera, screen, location, remote exec on another machine). |

---

**3. Gateway**

| What it is (other agent) | Why HomeClaw doesn’t have it / is it necessary? |
|-----------------------|---------------------------------------------------|
| The **gateway** tool is **admin/ops for the running Gateway process**: **restart** (e.g. SIGUSR1 in-place restart), **config.get** / **config.schema**, **config.apply** / **config.patch** (validate + write config + restart + wake), **update.run**. So: “restart the Gateway,” “change config and apply.” It’s a **single-process control plane**: the same process that runs the agent also exposes a tool to restart itself and edit its config. | **Different architecture**: HomeClaw has a **Core** (FastAPI), not a single “Gateway” process that owns channels + nodes + config in one. Restart and config are typically done **out of band** (stop/start the Core process, edit `core.yml` on disk). **Implementing it** would mean: a tool (e.g. `core_restart`, `config_apply`) that (a) writes config and (b) triggers a restart. Restart is process-lifecycle dependent (supervisor, Docker, systemd); not all deployments allow “restart self.” **Necessary?** For many deployments, **no**: operators restart the service and edit YAML by hand or via CI. For “agent can change its own config and restart” (risky), you could add a **restrictive** tool (e.g. allowlist, require a flag, audit log). **Verdict**: **Could implement** a narrow “config read/write + optional restart” tool with safeguards; **often not necessary** and can be security-sensitive. |

---

**4. Channel-specific message (other agent `message` tool)**

| What it is (other agent) | Why HomeClaw doesn’t have it / is it necessary? |
|-----------------------|---------------------------------------------------|
| The **message** tool lets the **agent send messages and channel actions** to the **channel the conversation came from** (or a session-bound target): **send** (text + optional media), **poll**, **react**, **read**, **edit**, **delete**, **pin**, **thread-***, **search**, **sticker**, **member-info**, **channel-info**, etc., for Discord, Slack, Telegram, WhatsApp, iMessage, MS Teams, Google Chat, Signal. So: “reply in this Slack thread,” “post a poll in this Discord channel,” “edit the last message.” The Gateway knows the **session’s channel** and routes the tool call to the right adapter. | **Different channel model**: In HomeClaw, **channels are separate processes** (or external bots). The Core receives a request (e.g. from the Telegram channel via `/inbound`) and returns a **single reply** (text or response payload). The **channel** is responsible for **sending** that reply to the user (e.g. send a Telegram message). So “reply to the user” is already **implicit**: the Core’s response *is* the reply. There is **no** in-turn “send a message to Slack” tool because the current turn’s output is already delivered by the channel that called Core. **Implementing it** would mean: (1) Core knows “this request came from channel X, session Y” and (2) a tool **message_send** (or **channel_send**) that takes text (and optional channel-specific args) and causes Core to **push** that content to that channel/session—e.g. Core calls back into the channel’s “send message” API, or the channel polls/WebSocket. That requires a **defined contract** (per channel: “how does Core send an extra message?”). Some channels already support “reply to this chat”; extending that to **rich actions** (poll, react, edit) is channel-specific. **Necessary?** For “the agent replies in the same chat,” **no**—that’s the default. For “the agent sends a **second** message, or a poll/reaction/edit in the same thread,” **yes** if you want feature parity with other agent’s message tool. **Verdict**: **Could implement** a **message_send** (and later channel-specific actions) if Core can invoke “send to this session/channel” via a small contract (e.g. callback URL or channel adapter interface). **Not necessary** for basic “agent replies once per turn”; **useful** for multi-message or rich channel actions. |

---

**Summary table**

| Item | Can implement? | Necessary? | Note |
|------|----------------|-----------|------|
| **Canvas** | No (needs node protocol + companion app) | No (unless you want device Canvas) | Tied to other agent nodes. |
| **Nodes** | No (needs full node stack + devices) | No (unless you want camera/screen/location/remote exec) | Tied to other agent ecosystem. |
| **Gateway** | Yes (narrow: config read/write + optional restart, with safeguards) | Often no (ops do it out of band) | Security-sensitive; optional. |
| **Message** | Yes | Useful for multi-message | HomeClaw implements **channel_send** with “last channel” logic (see below). |

**Design takeaway (why we skip Canvas, Nodes, Gateway; why channel_send is enough)**

- **Canvas**: Displaying a “canvas” of the home computer on a mobile device adds complexity and is rarely necessary; we don’t need it.
- **Nodes**: We already have **channels** to talk to HomeClaw and the Core can control the **current** machine (exec, browser). Controlling *another* computer via nodes is redundant: run another HomeClaw instance on that computer instead. Nodes add complexity without clear benefit for our design.
- **Gateway**: We have a **Core** and **channels**, not a single “Gateway” process. We only need to operate Core and channels; no need for a gateway admin tool.
- **Channel-specific message**: Sending **more than one continuous message** to one channel is useful (other agent can do this; default HomeClaw is “one request → one reply”). **Simple approach**: record which channel was used to send the last response; send any follow-up messages to that same channel. We don’t need multiple channels at the same time. HomeClaw already has **latestPromptRequest** (last request/channel); **channel_send** calls **send_response_to_latest_channel** so the agent can send additional messages to that channel. So: **channel_send** implements “send to last-used channel” and covers the useful part of other agent’s message tool for single-channel use.

#### Summary

- **Tools**: Reuse by **capability** (we have our own); not by **code** (other agent’s are Node/TS).
- **Skills**: Reuse by **format** (SKILL.md) and **catalog** (ClawHub bundles): load SKILL.md into HomeClaw’s context; optionally run skill scripts via a dedicated tool. No need to run the other agent Gateway.

---

### 7.11 Gap analysis: other agent modules we don't have (and whether they're necessary)

This subsection lists **modules or features other agent has that HomeClaw does not**, and for each whether we consider it **necessary to have** for HomeClaw.

#### Summary table

| other agent module / feature | HomeClaw status | Necessary? | Notes |
|---------------------------|-------------------|------------|--------|
| **Tools: canvas** | Out of scope | **No** | Requires node protocol + companion app; see §7.10.2. |
| **Tools: nodes** | Out of scope | **No** | Camera, screen, location, remote exec on devices; requires full node stack; see §7.10.2. |
| **Tools: gateway** | Out of scope | **No** | Restart/config tool for single Gateway process; we have Core + channels; ops do config/restart out of band; see §7.10.2. |
| **Tools: message (rich)** | Partial (**channel_send** only) | **Useful, not required** | We have "send to last channel"; other agent has poll, react, edit, delete, etc. Basic reply is covered. |
| **run_skill** (execute skill scripts) | **Implemented** | Yes | Tool **run_skill** in tools/builtin.py; runs scripts under skill's scripts/ with allowlist (config tools.run_skill_*). |
| **Onboarding / doctor** | **Implemented** | Yes | `python -m main onboard` (wizard for workspace, LLM, skills, tools); `python -m main doctor` (config + LLM connectivity check). |
| **Remote access / auth** | **Implemented** | Yes | **auth_enabled** + **auth_api_key** in config; /inbound and /ws require X-API-Key or Bearer. **docs/RemoteAccess.md** (Tailscale + API key). |
| **Session model (main vs group, activation, queue)** | Single Core; user/session/run | **Optional** | other agent: multi-conversation routing, mention activation, reply-back. We have sessions; no "main vs group" or activation model. |
| **Companion apps / Control UI** | None (WebSocket /ws for future WebChat) | **Optional** | other agent: macOS app, iOS/Android nodes, Control UI. Nice to have, not required for core assistant. |

#### Necessary to add (priority) — all implemented

1. **run_skill** — **Done.** Tool runs a script from a loaded skill's `scripts/` folder (skill_name + script; optional args). Config: `tools.run_skill_allowlist`, `tools.run_skill_timeout`.
2. **Onboarding / doctor** — **Done.** `python -m main onboard` (wizard); `python -m main doctor` (config + LLM connectivity).
3. **Remote access / auth** — **Done.** Core auth: `auth_enabled` + `auth_api_key`; /inbound and /ws require X-API-Key or Bearer. **docs/RemoteAccess.md** documents built-in auth and recommended path (Tailscale, Tailscale Funnel + auth proxy).

#### Not necessary (by design)

- **Canvas, nodes, gateway** — Already covered in §7.10.2: tied to other agent's node/Gateway stack; we don't need device Canvas, device control, or gateway self-admin for our design.
- **Richer message tool** — channel_send (last channel) covers "send another message to the same place"; poll/react/edit are channel-specific and can be added later if a channel supports them.
- **Session model (main vs group, activation)** — We have sessions and runs; multi-agent routing can be done with workspace_dir + multiple instances; activation (e.g. mention) is channel-specific.
- **Companion apps** — WebChat over /ws is a natural next step; full Control UI or device nodes are optional.

#### Summary

- **Necessary and implemented:** **run_skill**, **onboarding/doctor**, **remote access/auth** (Core API key for /inbound and /ws; see docs/RemoteAccess.md and Tailscale recommendation).
- **Not necessary:** Canvas, nodes, gateway; richer message (we have channel_send); full session model; companion apps (optional).

---

## 8. References

- **HomeClaw**: `Design.md`, `Improvement.md`, `docs/RemoteAccess.md`, `docs/Multimodal.md`, `channels/README.md`, `channels/telegram/README.md`, `channels/webhook/README.md`
- **other agent**: (other project), (external docs), [Templates: AGENTS / SOUL / TOOLS]((external docs)reference/templates/AGENTS), [Session model]((external docs)concepts/session), [ClawHub]((external docs)clawdhub) (skill registry), [Skills]((external docs)tools/skills)
