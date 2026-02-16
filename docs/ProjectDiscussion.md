# HomeClaw — Project Discussion

This document records an assessment and discussion of the HomeClaw project (architecture, strengths, trade-offs, and possible next steps). It is intended as a **living document**: use it as a base and improve it over time as the project and your goals evolve.

**Started:** 2025-02 (from a conversation with an AI assistant after reviewing README.md, Design.md, Channel.md, and the docs folder.)

---

## 1. What Stands Out

### 1.1 Clear separation of concerns

- **Core** = one brain; **channels** = many entry points.
- The same agent, memory, and tools regardless of how the user connects (email, Matrix, Telegram, CLI).
- Easy to reason about and extend: a new channel is an adapter, not a new “agent.”

### 1.2 “Minimal API” for bots

- **POST /inbound** with `{ user_id, text }` plus a **Webhook** relay means any bot (Telegram, Discord, n8n, custom script) can talk to Core without implementing a full `BaseChannel`.
- Full channels only when needed (e.g. WhatsApp Web session); thin HTTP when not.

### 1.3 Local-first, but not dogmatic

- Default is local (llama.cpp, GGUF), with cloud (LiteLLM) as an option.
- Main and embedding models can be chosen independently.
- Fits “run at home, scale or fallback in cloud” without forcing one or the other.

### 1.4 Three extension layers with clear roles

- **Tools** = atomic, composable (file, exec, browser, cron, memory, run_skill, route_to_plugin).
- **Skills** = tool-driven workflows (SKILL.md + optional scripts).
- **Plugins** = feature bundles (weather, news, mail) with their own code.

The doc that spells out “tools = building blocks, skills = workflows, plugins = one dedicated thing” (and how the LLM chooses) is a strength and avoids “everything is a plugin” or “everything is a tool” confusion.

### 1.5 Documentation

- Design.md, Channel.md, Comparison.md, and the docs/ folder give a consistent mental model: data flow, config, multi-user, memory backends, TAM vs cron, etc.
- Makes the project discussable and onboardable.

---

## 2. Trade-offs and Design Choices

### 2.1 Core + separate channel processes

- Channels are **separate processes** (or external bots) that call Core, unlike “one Gateway process with all channel code inside.”
- **Upside:** Clear boundary; channels can crash/restart without killing Core; can scale or place them separately.
- **Cost:** More things to run and wire (Core + N channels, env, ports).

*Note:* For a home / single-instance setup, “one process to rule them all” is simpler to run; for multi-machine or “channel as a service,” the current split makes sense. So it’s a deliberate trade-off.

### 2.2 One agent, multiple LLMs

- Current model: **one identity**, one workspace, one tool/skill set; you switch *which* LLM is used (main_llm, embedding_llm, or per-call), not “which agent.”
- Fits “one assistant, many models” (e.g. small model for spawn, big for hard questions).
- Multi-agent (different personas, different tools per “agent”) is explicitly deferred and described as a possible evolution in Design.md.

*Suggestion:* Keep the current default; add multi-agent only when there’s a concrete need (e.g. “support bot” vs “coder bot” with different TOOLS.md / workspace).

### 2.3 Memory: Cognee vs in-house chroma

- Default **Cognee** gives one stack (SQLite + Chroma + Kuzu, or Postgres/Qdrant/Neo4j via Cognee).
- In-house **chroma** backend remains for people who want everything in core.yml and no Cognee dependency.
- **Risk:** Two code paths and two doc streams (Cognee’s vs HomeClaw’s).
- **Benefit:** Not blocked on Cognee for every feature; power users can stay “core.yml only.”

*Suggestion:* Long term, one path may become clearly primary (likely Cognee), with the other “supported but not the default,” and docs reflecting that.

### 2.4 Plugins don’t call the tool registry

- Plugins use Core’s **programmatic API** (LLM, channel, chat) and don’t go through the same tool registry the main agent uses.
- So a plugin can’t “call file_read or web_search” as tools; it does its own HTTP, etc.
- **Upside:** Keeps plugins simple; avoids “plugin runs tool loop” complexity.
- **Future:** The doc’s idea of optionally letting plugins expose tools (or receive a tool executor) is a natural next step if you want plugins to reuse the same building blocks as the main agent.

---

## 3. Possible Priorities (for discussion)

These are suggestions to consider, not a fixed roadmap.

1. **Run experience**  
   A single entry point (e.g. “start Core + WebChat + Webhook” or “start Core + one channel from config”) would help. Even a small launcher script or a docker-compose-style one-command start could make the “many processes” model feel manageable.

2. **Local + cloud mix (see Roadmap.md)**  
   Routing by task (e.g. “simple → local, complex → cloud”) and fallback when local fails would make the “local-first but flexible” story concrete. Design now, implement when ready.

3. **WebChat as the “face” of HomeClaw**  
   With WebSocket `/ws` and auth (RemoteAccess.md), a solid WebChat UI is the main way people “see” the agent. Investing there (and maybe a simple “open WebChat” from CLI or launcher) could make demos and daily use much easier.

4. **Plugin parameter collection**  
   PluginParameterCollection.md (profile + config + confirm when uncertain) is the right direction. Implementing it would make “buy me milk” / “send email to X” style plugins more reliable and user-friendly.

---

## 4. Summary (one paragraph)

HomeClaw feels like a **thoughtful, doc-driven** local-first agent: clear architecture, explicit extension model (tools / skills / plugins), and honest trade-offs (separate processes, one agent, two memory backends). The main levers to pull next, from this discussion, are **operational simplicity** (how you run it), **local/cloud mix**, and **WebChat + parameter collection** so the agent feels “complete” in use.

---

## 5. Changelog / Notes (for future edits)

Use this section to record updates as you refine this doc.

| Date       | Change |
|------------|--------|
| 2025-02    | Initial version from conversation: strengths, trade-offs, priorities. |

---

## 6. Related docs

- **Design.md** — Architecture, components, data flow.
- **Channel.md** — Channels (users + developers).
- **Comparison.md** — HomeClaw vs other agent.
- **Roadmap.md** — Planned directions (local+cloud mix, etc.).
- **ToolsSkillsPlugins.md** — How tools, skills, and plugins work and how the LLM chooses.
- **PluginParameterCollection.md** — Parameter resolution and confirmation.
- **RemoteAccess.md** — Auth and remote access.
