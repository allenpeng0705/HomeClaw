# Deep Agents (LangChain) — Comparison and What We Can Learn

This doc summarizes [LangChain Deep Agents](https://github.com/langchain-ai/deepagents) and how it relates to HomeClaw: overlap, gaps, and practical takeaways. It does **not** recommend replacing HomeClaw with Deep Agents; it identifies ideas worth adopting and when integration might be useful.

---

## 1. What Deep Agents Is

- **Agent harness**: Batteries-included agent built on LangChain + LangGraph. One call (`create_deep_agent()`) gives you an agent with planning, filesystem, shell, and sub-agents.
- **Included capabilities**:
  - **Planning** — `write_todos` tool for task breakdown and progress tracking (model updates a todo list as it works).
  - **Filesystem** — `read_file`, `write_file`, `edit_file`, `ls`, `glob`, `grep` with **pluggable backends**: in-memory, local disk, LangGraph store, **sandboxes** (Modal, Daytona, Deno), or custom.
  - **Shell** — `execute` with sandboxing.
  - **Sub-agents** — `task` tool to spawn a subagent with **isolated context** (clean context window for the subtask).
  - **Context management** — Auto-summarization when conversations get long; large tool outputs saved to files to avoid context overflow.
- **Runtime**: Returns a compiled **LangGraph** graph — streaming, persistence, checkpointing, human-in-the-loop.
- **CLI**: Terminal coding agent (Textual UI) with web search, remote sandboxes, persistent memory, approval flows.
- **Security**: “Trust the LLM” — enforce boundaries at **tool/sandbox** level, not by expecting the model to self-police.
- **MCP**: Supported via `langchain-mcp-adapters`.

---

## 2. HomeClaw vs Deep Agents (High Level)

| Area | Deep Agents | HomeClaw |
|------|-------------|----------|
| **Planning** | `write_todos` — model explicitly maintains a todo list and ticks items. | Planner–Executor: one LLM call → JSON plan (goal + steps) → executor runs steps. DAG for fixed flows (search_web, send_email). No user-visible “todo list” the model updates. |
| **Filesystem** | Virtual FS with pluggable backends (memory, disk, store, sandboxes). | Fixed sandbox (documents/, output/, etc.) + `file_read` / `file_write` / `folder_list` / `document_read`. No pluggable backends. |
| **Shell** | `execute` with sandboxing (e.g. Modal, Daytona). | `exec` with allowlist; no remote/sandbox backends. |
| **Sub-agents** | `task` — spawn with isolated context window. | `sessions_spawn` — one-off task, optional different model; session/context isolation is per-session, not explicitly “clean context for this subtask.” |
| **Context / long convos** | Auto-summarization; large outputs to files. | Memory (RAG + agent_memory), save_result_page, needs_llm_tools; no built-in “summarize when long” step. |
| **Runtime** | LangGraph (streaming, checkpoints, persistence). | Custom loop (ReAct, DAG, planner-executor); no LangGraph. |
| **Memory** | LangGraph Memory Store across threads. | Chroma RAG + composite backend, agent_memory, daily memory, TAM. |
| **Front-ends** | CLI (Textual), SDK `invoke()`. | Core API, Companion app, channels, WebSocket, TAM. |

**Conclusion**: We already cover similar ground (planning, files, exec, spawn, memory). Deep Agents emphasizes **explicit todo UX**, **pluggable filesystem/sandboxes**, and **LangGraph-native** runtime. HomeClaw emphasizes **intent routing**, **skills/plugins**, **local/cloud mix**, and **multi-channel/companion**.

---

## 3. What We Can Learn (Without Integrating)

### 3.1 Todo-style planning UX

- **Idea**: Expose planning as a **tool** the model uses: e.g. `write_todos([...])` and “tick” steps as done, so the user (and the model) see progress.
- **HomeClaw today**: Plan is internal (JSON steps); user sees final result or intermediate tool outputs, not “Step 1/3 done.”
- **Takeaway**: Consider a **lightweight** “plan progress” surface: e.g. a tool or structured message that updates “Current plan: 1. … 2. … 3. …” and “Completed: 1, 2” so long tasks feel more transparent. Optional; not a requirement.

### 3.2 Pluggable filesystem / sandbox backends

- **Idea**: Abstract “where files live” and “where code runs”: in-memory, local disk, cloud store, or **remote sandbox** (Modal, Daytona, Deno).
- **HomeClaw today**: Single sandbox (documents/, output/, etc.); `exec` is local with allowlist.
- **Takeaway**: If we add “run in sandbox” or “save to cloud,” a **backend abstraction** (read_file/write_file/exec behind an interface) would let us plug local vs sandbox vs cloud without rewriting every tool. Lower priority unless we explicitly add remote execution or cloud file storage.

### 3.3 Context management: large outputs and summarization

- **Idea**: When a tool returns a lot of text, **save to file and inject a short summary** (or link) into the conversation so we don’t blow the context window; optionally **summarize** long conversations.
- **HomeClaw today**: `save_result_page`, `needs_llm_tools` (so raw big results get a second LLM pass); we don’t have an explicit “summarize this turn when content > N chars” step.
- **Takeaway**: Strengthen **prompts or a small helper**: e.g. “If the last tool result is very long, write a brief summary to the user and/or save the full content to a page and return the link.” Optionally: a **configurable threshold** (e.g. tool result > 8k chars → save to file + summarize in reply). This is a low-effort, high-value improvement.

### 3.4 Sub-agent context isolation

- **Idea**: When spawning a sub-agent, start with a **clean context** (no prior conversation) so the subtask doesn’t inherit irrelevant tokens.
- **HomeClaw today**: `sessions_spawn` runs a one-off; we can pass a fresh session or minimal context, but it’s not documented as “isolated context window” the way Deep Agents’ `task` is.
- **Takeaway**: Document (and optionally enforce) that **sessions_spawn** is used with **minimal or empty history** for the sub-task so the main agent’s long context doesn’t leak in. No API change required; clarify in tool description and docs.

### 3.5 Security

- **Idea**: “Trust the LLM” — don’t rely on the model to refuse; enforce at **tool and sandbox** level (allowlists, sandbox boundaries).
- **HomeClaw**: We already do this (exec allowlist, file sandbox). Aligns with our approach; no change needed.

---

## 4. Is Integration Useful?

### 4.1 Using Deep Agents *as* HomeClaw’s engine

- **Pros**: LangGraph runtime (streaming, checkpointing), battle-tested harness, MCP.
- **Cons**: Large refactor (our loop, intent router, DAG, skills, plugins, TAM, memory are all custom). We’d lose tight control over local/cloud mix, companion, and multi-channel. Not recommended.

### 4.2 Using Deep Agents as a **sub-component** (e.g. one skill or “research agent”)

- **Possible**: Run Deep Agents in a subprocess or as a library for a **specific** use case (e.g. “research and write a report” using their SDK). HomeClaw would call it like a skill or `sessions_spawn` target.
- **Trade-off**: Adds LangChain/LangGraph as a dependency for that path; we already have `web_search`, `tavily_research`, planner-executor, and skills. Only worth it if we want their **sandboxes** (Modal, Daytona, Deno) or their **CLI** as an alternative front-end for power users.
- **Recommendation**: **Optional** integration only if we explicitly want remote sandbox execution or their CLI. Otherwise, adopt **ideas** (todos UX, context/summarization, isolation) without adding the dependency.

### 4.3 When integration *might* be worth it

- We want **remote/sandboxed execution** (e.g. “run this code in Modal”) and prefer reusing their adapters rather than building our own.
- We want to offer a **terminal coding agent** (like their CLI) and are okay maintaining a separate front-end that talks to Core or to Deep Agents.
- We decide to **migrate** to LangGraph long-term and use Deep Agents as the harness on top; that’s a strategic, multi-quarter decision, not a quick win.

---

## 5. Summary

| Question | Answer |
|----------|--------|
| **What can we learn?** | Todo-style planning UX, pluggable file/sandbox backends (for future use), stronger “large output → save + summarize” behavior, and explicit sub-agent context isolation. |
| **Integrate Deep Agents into HomeClaw?** | Not as the core engine. Only as an **optional** sub-component if we need their sandboxes or CLI; otherwise adopt ideas and keep our stack. |
| **Immediate, low-effort wins** | (1) Prompt or helper: “when tool result is very long, save to file and summarize in reply.” (2) Document `sessions_spawn` as “use with minimal/empty context for isolation.” (3) Optionally add a simple “plan progress” hint (e.g. “Steps: 1/3 done”) for long planner-executor runs. |

---

## 6. Implementation status (learnings adopted)

| Learning | Status | Where |
|----------|--------|--------|
| **Large tool result → save + summarize** | Done | When last tool result length > `tools.large_result_summarize_threshold_chars` (default 6000; 0 = off), we inject an instruction in the "Handling tool results" block so the LLM summarizes and/or calls `save_result_page` and returns the link. Config: `large_result_summarize_threshold_chars` under `tools` in skills_and_plugins.yml. |
| **Sub-agent context isolation** | Done | `run_spawn` already uses isolated context (no RAG, no tools, no prior conversation). Docstring and tool description updated: `sessions_spawn` and `agents_list` message now state "isolated context (no prior conversation)" and "ideal for a focused subtask." |
| **Plan progress** | Done | In `build_final_summary_messages` we prepend "Plan progress: N/N steps completed." to the execution summary so the final-summary LLM (and any logging) sees step count. |
| **Pluggable backends** | Deferred | Not implemented; add when we introduce remote sandboxes or cloud file storage. |

---

## References

- [Deep Agents GitHub](https://github.com/langchain-ai/deepagents)
- [Deep Agents docs (overview)](https://docs.langchain.com/oss/python/deepagents/overview)
- HomeClaw: `docs_design/PlannerExecutorAndDAG.md`, `docs_design/SessionAndDualMemoryDesign.md`, `docs_design/ToolsDesign.md`
