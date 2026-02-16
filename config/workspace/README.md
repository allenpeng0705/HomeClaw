# Workspace bootstrap (prompt engineering)

The files in this folder are **injected into the system prompt** sent to the LLM on every reply. They are used for **prompt engineering only** — edit the markdown to change behavior; no code runs from these files.

---

## Workspace vs memory: how they work together

**Workspace** and **memory** both feed the LLM, but they are different kinds of input and come from different places.

| | **Workspace** (this folder) | **Memory** (RAG + chat) |
|---|-----------------------------|--------------------------|
| **What it is** | Static prompt text: *who* the assistant is and *what* it can do. | Dynamic context: *what was said* (chat) and *what to recall* (RAG). |
| **Where it lives** | Markdown files on disk: `config/workspace/IDENTITY.md`, `AGENTS.md`, `TOOLS.md`. | **Chat**: SQLite (recent turns). **RAG**: Chroma (vector store) + embedding model. |
| **When it changes** | When you edit the .md files and restart (or on next request if you don’t cache). Same for all users/sessions. | **Chat**: every turn (new message + reply). **RAG**: when new content is added to the vector store (e.g. from `memory_queue`). Per user/session/run. |
| **How the LLM sees it** | First part of the **system** message: “## Identity”, “## Agents / behavior”, “## Tools / capabilities”. | **System**: “Here is the given context: …” (RAG snippets). **Messages**: recent chat (user/assistant turns) + current user message. |
| **Purpose** | Set identity and capabilities so the model knows *who it is* and *what it’s allowed to do*. | Give the model *what was said* (chat) and *what to remember* (RAG) so it can answer in context. |

So:

- **Workspace** = fixed “personality + capabilities” (prompt engineering). Same text every time until you change the files.
- **Memory** = changing “conversation + recalled facts” (data). Different per user, session, and what’s in the DB/Chroma.

Both are combined into one **system** message (workspace block + RAG template with memories), then **messages** (chat history + current query) are appended. The model then generates a reply; that turn is saved to **chat** (SQLite) and optionally enqueued for **RAG** (embed → Chroma).

**Flow in one sentence:**  
On each user message, Core loads **workspace** from disk, loads **recent chat** from SQLite, fetches **relevant memories** from Chroma, builds the system prompt (workspace + RAG context), appends messages (chat + current query), calls the LLM, then saves the new turn to chat and may add to RAG.

**Flow step by step** (where workspace and memory are used):

1. User sends a message → Core enters `answer_from_memory()`.
2. **Workspace**: If `use_workspace_bootstrap` is true, Core calls `load_workspace()` (reads IDENTITY.md, AGENTS.md, TOOLS.md from disk) and `build_workspace_system_prefix()` → appends that block to `system_parts`.
3. **Memory (RAG)**: If `use_memory` is true, Core calls `_fetch_relevant_memories(query, …)` → embeds the query, searches Chroma (vector store), gets top‑k similar snippets → builds `memories_text` → fills `RESPONSE_TEMPLATE` with “Here is the given context: …” → appends that to `system_parts`.
4. **Memory (chat)**: The `messages` argument already contains recent chat (loaded earlier from SQLite, e.g. last 6 turns) plus the current user message.
5. Core builds one system message: `content = "\n".join(system_parts)` (workspace + RAG template), then `llm_input = [{"role": "system", "content": content}] + messages`.
6. Core calls the LLM with `llm_input`; LLM returns the reply.
7. Core saves the turn to **chat** (SQLite) and may have enqueued the request to **memory_queue** so a background worker adds it to **RAG** (embed → Chroma).

So workspace is used in step 2 (disk → system_parts); memory is used in step 3 (Chroma → system_parts) and step 4 (SQLite → messages).

---

## Files and order in the system prompt

| File | Role | Header in system message |
|------|------|---------------------------|
| **IDENTITY.md** | Who the assistant is (tone, voice, style) | `## Identity` |
| **AGENTS.md** | High-level behavior and routing hints | `## Agents / behavior` |
| **TOOLS.md** | Human-readable list of capabilities | `## Tools / capabilities` |

They are concatenated in that order, then the **RAG response template** (with “Here is the given context: …” and guidelines) is appended. So the full system message is:

```
## Identity
< content of IDENTITY.md >

## Agents / behavior
< content of AGENTS.md >

## Tools / capabilities
< content of TOOLS.md >

< RAG response template with memories context and guidelines >
```

After that, the **messages** (recent chat history + current user message) are sent. So the model sees: **identity → agents → tools → RAG context → conversation**.

---

## Where injection happens (code)

1. **Core** (`core/core.py`): In `answer_from_memory()`, a list `system_parts` is built:
   - If `use_workspace_bootstrap` is true in `core.yml`, the workspace block is loaded and appended first.
   - Then the RAG response template (with memories) is appended.
   - Final system message: `llm_input = [{"role": "system", "content": "\n".join(system_parts)}]`, then `llm_input += messages`.

2. **Loader** (`base/workspace.py`):
   - `load_workspace()` reads `IDENTITY.md`, `AGENTS.md`, `TOOLS.md` from this directory (or a configured path).
   - `build_workspace_system_prefix(workspace)` builds the single block with headers `## Identity`, `## Agents / behavior`, `## Tools / capabilities` and the file contents. Only non-empty files are included.

3. **Config** (`config/core.yml`): `use_workspace_bootstrap: true` enables injection. Set to `false` to disable.

---

## Tips

- Keep each file short: a few bullets or short paragraphs. Long text uses context and can dilute the RAG guidelines.
- Leave a file empty or delete it to skip that block.
- See `Comparison.md` §7.4 and `Design.md` §3.4 for the design and “session transcript” vs “identity/capabilities” split.
