# Review: Changes and Positioning vs other agent

This document reviews the changes made to HomeClaw (multi-agent paths, sessions_spawn, capability-based LLM selection, channel_send, last-channel store, and the decision to skip Canvas/Nodes/Gateway). It assesses whether each change is **reasonable**, **necessary**, and whether it supports our goals: **simpler**, **easier to deploy**, **easier to extend**—and **better than other agent** on those dimensions where we choose to differ.

---

## 1. Summary of Changes (What We Did)

| Area | What changed |
|------|----------------|
| **Multi-agent paths** | Added `workspace_dir` to config; documented two paths: (1) single Core, switch workspace by config/time, (2) multiple HomeClaw instances. |
| **sessions_spawn** | Sub-agent one-off run: `Core.run_spawn(task, llm_name)`, tool `sessions_spawn` with optional `llm_name` or `capability`. |
| **Per-call LLM** | `Util.openai_chat_completion(..., llm_name=None)`, `_resolve_llm(llm_name)`; any caller can use a different model per call. |
| **Capability-based selection** | `Util.get_llm_ref_by_capability(capability)`; `models_list` returns refs + capabilities; `sessions_spawn` accepts `capability` (e.g. "Chat"). |
| **models_list tool** | Tool returns `models`, `model_details` (ref, alias, capabilities), `main_llm` so the agent can choose by ref or capability. |
| **channel_send** | Tool that sends an additional message to the last-used channel via `send_response_to_latest_channel`. |
| **Last-channel store** | Robust persistence: SQLite table `homeclaw_last_channel` + atomic file `database/latest_channel.json`; `base/last_channel.py` save/get; Core persists on every request and loads from store when in-memory is missing. |
| **Canvas, Nodes, Gateway** | Decided **not** to implement; documented why (unnecessary, add complexity). Message parity covered by **channel_send** with “last channel” logic. |
| **Docs** | Design.md (workspace_dir, last-channel store, multi-agent paths); Comparison.md (tool parity, §7.10.2 review, design takeaway). |

---

## 2. Assessment by Goal

### 2.1 Simpler

| Change | Simpler? | Note |
|--------|----------|------|
| **workspace_dir** | ✅ Yes | One config key; no agent registry or routing logic. Switch agent = switch directory. |
| **sessions_spawn + llm_name/capability** | ✅ Yes | One tool, two ways to pick model (ref or capability). No separate “sub-agent service.” |
| **models_list** | ✅ Yes | Single source of truth for “what models exist and what they can do.” |
| **channel_send** | ✅ Yes | One tool: “send this text to the last-used channel.” No channel-specific adapters or message API. |
| **Last-channel store** | ✅ Yes | One table + one file; atomic write; no custom protocol. Replaces ad-hoc “one file in project root.” |
| **Skip Canvas/Nodes/Gateway** | ✅ Yes | Fewer concepts: no nodes, no gateway process, no canvas protocol. We stay “Core + channels + tools.” |

**Verdict**: All changes either add a single, clear mechanism (workspace_dir, channel_send, last-channel store) or explicitly avoid complexity (no Canvas/Nodes/Gateway). No unnecessary abstraction.

---

### 2.2 Easier to Deploy

| Change | Easier to deploy? | Note |
|--------|--------------------|------|
| **workspace_dir** | ✅ Yes | Copy another `config/workspace_*` dir and set one key; no extra processes. |
| **sessions_spawn** | ✅ Yes | No separate “spawn service”; same Core process. Optional llm_name/capability from existing config. |
| **models_list / capability** | ✅ Yes | Uses existing `local_models` / `cloud_models` in `core.yml`; no new config surface. |
| **channel_send** | ✅ Yes | Works with existing channels; no new ports or gateways. |
| **Last-channel store** | ✅ Yes | Uses existing SQLite (same DB as chat) + one file under `database/`; no new infrastructure. |
| **Skip Canvas/Nodes/Gateway** | ✅ Yes | No companion apps, no node host, no gateway admin; deploy = Core + channels. |

**Verdict**: No new moving parts for deployment. Everything reuses Core, existing config, and existing DB/file layout.

---

### 2.3 Easier to Extend

| Change | Easier to extend? | Note |
|--------|--------------------|------|
| **workspace_dir** | ✅ Yes | Add a new “agent” = add a new workspace dir and point `workspace_dir` at it (or switch by time/script). |
| **Per-call llm_name** | ✅ Yes | New tools or plugins can call a different model without changing global main_llm. |
| **Capability** | ✅ Yes | Add a new capability in config; selection logic stays in one place (`get_llm_ref_by_capability`). |
| **models_list** | ✅ Yes | New models in config automatically appear in the tool; no code change. |
| **channel_send** | ✅ Yes | New channels only need to implement the same response contract; no tool changes. |
| **Last-channel store** | ✅ Yes | Optional: add per-session key later (e.g. `app_id:user_id:session_id`) without changing the tool API. |

**Verdict**: Extension is mostly config and optional new workspace dirs; minimal code paths for “new agent” or “new model.”

---

## 3. Are These Changes Reasonable and Necessary?

| Change | Reasonable? | Necessary? |
|--------|-------------|------------|
| **workspace_dir** | ✅ Yes. Single knob to switch identity/tools description; no over-engineering. | ✅ Yes, if you want “one agent by day, another at night” or multiple agents without multi-process. |
| **sessions_spawn** | ✅ Yes. Matches “sub-agent run” in one process with optional different LLM. | ✅ Yes, for other agent-style parity and for delegated tasks without starting another session. |
| **Per-call llm_name** | ✅ Yes. Small addition to Util; no global state change. | ✅ Yes, for spawn and future tools (e.g. vision, fast vs slow model). |
| **Capability-based selection** | ✅ Yes. Uses existing `capabilities` in config; one resolver. | ⚠️ Nice-to-have. Ref-based selection is enough; capability makes prompts simpler (“use Chat”) and avoids hardcoding refs. |
| **models_list** | ✅ Yes. Read-only; reflects config. | ✅ Yes, so the agent (and users) know which refs/capabilities exist. |
| **channel_send** | ✅ Yes. One tool, one responsibility. | ✅ Yes, for “multiple continuous messages” without building a full message API. |
| **Last-channel store** | ✅ Yes. DB + atomic file is a standard pattern; survives restart. | ✅ Yes, so channel_send and plugins work after restart and are not tied to a single file in project root. |
| **Skip Canvas/Nodes/Gateway** | ✅ Yes. Documented; no half-implemented features. | ✅ Yes, to stay simple and avoid other agent-specific stack. |

**Overall**: All changes are reasonable. Most are necessary for parity (spawn, multi-message) or robustness (last-channel store); capability and models_list improve usability and extendibility without adding deployment cost.

---

## 4. Better Than other agent (On Our Terms)

We are **not** trying to clone other agent. We are trying to be **simpler, easier to deploy, and easier to extend**. On that basis:

| Dimension | other agent | HomeClaw after these changes |
|-----------|----------|----------------------------------|
| **Simplicity** | Gateway + nodes + canvas + many tools + session model | Core + channels + tools; no nodes/canvas/gateway; one workspace_dir; one “last channel.” |
| **Deployment** | Single Gateway (or gateway + node hosts); companion apps for canvas/nodes | Core + channels; optional workspace dirs; SQLite + file; no companion apps. |
| **Extensibility** | New agent = workspace + config; new tool = plugin | New agent = workspace dir + workspace_dir (or new instance); new model = config + optional capability; new channel = same contract. |
| **Tool parity** | Full set including canvas, nodes, gateway, message | Same set **except** canvas, nodes, gateway; message → channel_send (last channel). |
| **Multi-agent** | In-process multi-agent + sessions | Two paths: switch workspace (one at a time) or multiple instances. |

So we are **simpler and easier to deploy** by doing less (no nodes/canvas/gateway) and by reusing one Core and one store. We are **easier to extend** by keeping extension points clear (workspace_dir, config models, capability, last-channel store). We are **better on our terms** when “simple, deployable, extensible” matter more than “every other agent feature.”

---

## 5. Design choices (no further trim)

- **Capability**: We **keep** capability-based selection. Capabilities in config tell us **which model can be selected for which task** (e.g. Chat for spawn, vision for image). That's why we have `get_llm_ref_by_capability` and `sessions_spawn(capability="Chat")`—so the agent (or tools) can pick the right model by task, not only by ref.
- **workspace_dir**: Core **only reads** `workspace_dir` from config (e.g. `config/workspace` or `config/workspace_night`). Core does **not** do time-based switching inside the process. If you want day vs night switching, you do it **outside** Core: e.g. a cron job or script that updates `workspace_dir` in `core.yml` and restarts Core, or you run two instances and route by time. So: one config key, no schedule logic in Core—simple and stable.
- **Last-channel**: We **keep both** SQLite table and atomic file for **stability**: DB for durable state and future per-session keys; file as fallback and atomic write. No plan to drop either.

---

## 6. Conclusion

- The changes are **reasonable and aligned** with the goals: simpler, easier to deploy, easier to extend.
- They are **necessary** for robust tool parity (sessions_spawn, channel_send, last-channel store) and for clear multi-agent options (workspace_dir, multiple instances) without adding Canvas/Nodes/Gateway.
- Together they make HomeClaw **better than other agent on our terms**: we do less (no nodes/canvas/gateway), we reuse one Core and one store, and we keep extension points explicit and config-driven.

No rollback recommended; capability, last-channel (DB + file), and workspace_dir (config-only, no schedule in Core) are intentional and kept as-is.
