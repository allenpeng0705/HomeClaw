# Folder semantics and path inference

This document pins down **exact semantics** for user sandbox folders, how Core resolves natural-language references (e.g. "my documents", "Sabrina's output"), and **inference** when the user does not specify a folder. It aligns with the multi-user/friends model and the sandbox layout in the design conversation.

**Related:** [UserFriendsModelFullDesign.md](UserFriendsModelFullDesign.md) (master design for user/friends, sandbox, memory, push); [FileSandboxDesign.md](FileSandboxDesign.md) (current implementation: sandbox, share, output); [MultiUserSupport.md](MultiUserSupport.md).

## Sandbox layout under `homeclaw_root`

Agreed structure (for implementation when moving to user/friend model):

| Path | Purpose | Who can access |
|------|---------|----------------|
| `homeclaw_root/share/` | Global share across all users | All users |
| `homeclaw_root/{user_id}/` | **User sandbox root** — default when nothing specified | That user (and Core on their behalf) |
| `homeclaw_root/{user_id}/downloads/` | User's downloads (see semantics below) | That user |
| `homeclaw_root/{user_id}/documents/` | User's documents ("my documents") | That user |
| `homeclaw_root/{user_id}/output/` | User's own generated output | That user |
| `homeclaw_root/{user_id}/work/` | Work-related files | That user |
| `homeclaw_root/{user_id}/share/` | Shared among that user's friends only | That user + friends in context |
| `homeclaw_root/{user_id}/{friend_id}/output/` | **Friend's generated files** (e.g. Sabrina's reports, PPTs) | That user (Core writes here, sends link) |
| `homeclaw_root/{user_id}/{friend_id}/knowledge/` | That friend's KB; used when chatting with that friend (RAG) | Core for that (user, friend) pair |

- **Default when nothing specified:** use the **user's root folder**: `homeclaw_root/{user_id}/`. File tools that receive an empty or unspecified path should resolve to this root (same as path `"."` today).

---

## Folder semantics

### `downloads/`

- **Meaning:** Files the **user** has explicitly saved or that **Core/Companion** has saved on their behalf (e.g. "save this to my downloads", export from Core, Companion "save to device" when configured to use this folder).
- **Scope:** Only files that Core or the Companion app writes into `homeclaw_root/{user_id}/downloads/`. We do **not** automatically include the OS/browser "Downloads" folder (e.g. browser-downloaded files). If we later support syncing or indexing the system Downloads folder, that would be a separate feature and documented as such.
- **Companion "save to device":** When the user taps "save to device" for a file Core sent, the Companion can save to the **device** (OS downloads/photos) and/or optionally upload/write a copy to `homeclaw_root/{user_id}/downloads/` so Core can refer to it later. Exact behavior is configurable; the important point is: **Core’s notion of "downloads"** = `{user_id}/downloads/` under homeclaw_root, unless we explicitly add another source (e.g. "also index ~/Downloads").

### `documents/`

- **Meaning:** The user’s own documents (tax docs, notes, PDFs, etc.) — i.e. "my documents" in natural language.
- **Path:** Always `homeclaw_root/{user_id}/documents/`.
- **Content:** No strict file-type rule; anything the user or Core places here is "documents". Core uses this when the user says "my documents", "in my docs", "the document I have", etc., without referring to a friend.

### `output/` (user’s own)

- **Meaning:** Files **the user** has generated or that Core has generated **as the user’s** output (e.g. "save the report to my folder" when the user is the author).
- **Path:** `homeclaw_root/{user_id}/output/`.
- **Distinction:** Versus **friend output** (below): "Sabrina’s output" is not here; it’s under `{user_id}/{friend_id}/output/`.

### `{friend_id}/output/` (friend’s output)

- **Meaning:** Files **that friend** (e.g. Sabrina) has generated for the user. Core writes here when a friend produces a report, image, or PPT and sends a link to the user.
- **Path:** `homeclaw_root/{user_id}/{friend_id}/output/`.
- **Resolution in prompts:** When the user says "the PPT Sabrina sent", "Sabrina’s report", "the file from Sabrina", "open what Sabrina made" → resolve to this folder (and optionally search/list here).

### `{friend_id}/knowledge/`

- **Meaning:** That friend’s knowledge base for the (user, friend) pair. RAG/Cognee use it when chatting with that friend; no separate "user KB" embedding required for that pair.
- **Path:** `homeclaw_root/{user_id}/{friend_id}/knowledge/`.
- **Not exposed as "my documents":** "My documents" always means the user’s `documents/`; friend knowledge is used internally for answers, not as a folder the user names in the same way.

### `work/`

- **Meaning:** Work-related files for that user. Used when the user says "my work folder", "work files", etc.
- **Path:** `homeclaw_root/{user_id}/work/`.

### `share/` (per-user)

- **Meaning:** Shared among **that user’s friends** only (not global). Use when the user says "our shared folder" or "what we share with the group".
- **Path:** `homeclaw_root/{user_id}/share/`.
- **Global share:** `homeclaw_root/share/` remains for cross-user shared content; path `share/...` in tools can stay as today (global) until we introduce per-user `{user_id}/share/` in the API.

---

## Resolving natural language to a folder

Core (and any tool that accepts a "folder" or "path" from the model) should resolve the following patterns so the model can pass the right path to file tools.

| User says (examples) | Resolved path (under `homeclaw_root/{user_id}/`) | Notes |
|---------------------|---------------------------------------------------|--------|
| "my documents", "my docs", "the document I have" | `documents/` | Never friend output or friend knowledge. |
| "Sabrina’s output", "the file Sabrina sent", "what Sabrina made", "the PPT from Sabrina" | `{friend_id}/output/` (e.g. `Sabrina/output/`) | friend_id = that friend’s id in user’s friends list. |
| "my downloads", "what I downloaded" (in Core/Companion sense) | `downloads/` | Only Core/Companion downloads folder; not browser Downloads unless we add that. |
| "my output", "my generated files", "the report I made" | `output/` | User’s own output. |
| "my work", "work folder", "work files" | `work/` | User’s work folder. |
| "our shared folder", "what we share" (among my friends) | `share/` (per-user) or global `share/` | Depends on product: per-user vs global; can start with global. |
| "share" (global) | `share/` (global) | Same as today: `homeclaw_root/share/`. |
| (nothing specified), "my folder", "my files", "save it", "put it in my folder" | **User root** `"."` → `homeclaw_root/{user_id}/` | **Default:** when no folder is specified, use user root. |

- **Ambiguity:** If the user says "the report" without saying who made it, Core can infer from context (e.g. last message was from Sabrina → try `{friend_id}/output/` first; otherwise user’s `output/` or user root).
- **Listing:** "What’s in my documents?" → list `documents/`; "What did Sabrina send me?" → list `{friend_id}/output/`.

---

## Inference when the user doesn’t specify a folder

- **Default path:** When the user does **not** specify a folder (e.g. "save it", "where did you put it?", "list my files"), Core should assume the **user’s root folder**: `homeclaw_root/{user_id}/` (i.e. path `"."` in the current resolution model). This is the single consistent default; no random or context-free subfolder.
- **Context-based refinement:** If the conversation is clearly about a specific area (e.g. "save that report" right after generating a report → could default to `output/`; "save that PDF" after user said "I got a tax doc" → could default to `documents/`), Core may infer that subfolder. When in doubt, **user root** is the safe default.
- **Implementation:** Path resolution (e.g. `_resolve_file_path`) should treat empty/missing path as user root (`"."`). Tool descriptions and system prompt should state: "When no path is given, the default is the user’s root folder (homeclaw_root/{user_id}/)."

---

## Summary

| Topic | Decision |
|-------|----------|
| **downloads** | Only Core/Companion-saved files in `{user_id}/downloads/`; not browser Downloads unless we explicitly add that. |
| **"My documents"** | Always `homeclaw_root/{user_id}/documents/`. |
| **"Sabrina’s output"** | Always `homeclaw_root/{user_id}/{friend_id}/output/`; resolve friend name → friend_id from user’s friends. |
| **Default when nothing specified** | User root: `homeclaw_root/{user_id}/` (path `"."`). |
| **Inference** | Core can infer folder from phrases like "my documents", "Sabrina’s file", "my downloads"; when vague, default to user root (and optionally refine from conversation context). |

This gives implementers and the model a single source of truth for folder semantics and default path behavior.
