# What content is stored in RAG for skills

This doc describes **what text is embedded and stored** in the skills vector store (RAG) and how retrieval works.

**Principle:** The embedding is **one index** for skills. We must use the **best content to index** (name + description + keywords) — **not all content**. The full SKILL.md (including body) is loaded into the prompt when a skill is selected; the index is only for **selection**.

---

## 1. Purpose of RAG for skills

RAG is used **only for selection**: which skills to put in the system prompt. When a skill is **selected**, the **full** SKILL.md (name, description, **body**) is loaded from disk and injected into the prompt. So we **do not store the body in the index** — we only need the index to match the user query to the right skills.

---

## 2. What **should** be stored (recommended)

| Part | Source | Required? | Why |
|------|--------|-----------|-----|
| **name** | SKILL.md frontmatter `name:` | Yes | Short label for the skill. |
| **description** | SKILL.md frontmatter `description:` | Yes | What the skill does; main signal for semantic match. |
| **keywords** | SKILL.md frontmatter `keywords:` | Optional | Improves match across languages and phrasings (e.g. "天气" for weather). |
| **body** | SKILL.md body | **No** | Body is long, often code/markdown; can dilute the embedding. The full body is already in the prompt when the skill is selected. |

**Recommended stored text:** `name` + `description` + `keywords` (no body). One vector per skill.

---

## 3. What is stored today (implementation)

The text that gets **embedded and stored** is built by **`build_skill_refined_text()`** in `base/skills.py`:

| Part | When included |
|------|----------------|
| **name** | Always (if set) |
| **description** | Always (if set) |
| **keywords** | If present in frontmatter |
| **trigger** | If present: first 200 chars of `trigger.instruction` + pattern terms (regex symbols stripped so e.g. `weather\|forecast\|天气` → "weather forecast 天气") so user phrases like "how's the weather" match. |
| **body** | Only if `refined_body_max_chars` > 0 at sync; default is **0** (body not stored). |

Parts are joined with newlines. So with default sync: stored string = **name** + **description** + **keywords** + **trigger** (instruction snippet + pattern words). That gives RAG enough signal for both semantic match and phrase match (including cross-lingual via keywords and trigger patterns).

The vector store stores: **id** = folder name, **embedding** = vector of that text, **payload** = `{ "folder", "name", "description" }` (metadata only; search is by embedding).

---

## 4. Sync parameters (Core startup)

- **refined_body_max_chars:** Passed to `build_skill_refined_text()`. Default **0** = do not store body. Set > 0 only if you want body snippet in RAG (usually not needed).
- **skills_test_dir:** If set, skills from that directory are also synced with id prefix `test__<folder>`.

---

## 5. Retrieval (search)

- The **user query** (e.g. “what’s the weather in London”) is embedded with the **same embedder**.
- Vector store returns the top **limit** (e.g. 10) by **cosine distance**; scores are converted to similarity as `1 - distance`.
- Results with similarity **below** `skills_similarity_threshold` (e.g. 0.3) are dropped.
- The remaining list is **capped to** `skills_max_in_prompt` (e.g. 5).
- Those skill **folder names** are used to load the full skill (name, description, body) from disk and build the “Available skills” block for the system prompt. So **retrieval** uses only the stored embedding (from the refined text); the **prompt** gets the full skill content from SKILL.md.

---

## 6. Summary table

| What | Where | Content |
|------|--------|--------|
| **Stored in RAG (one vector per skill)** | Chroma collection `homeclaw_skills` | **name** + **description** + **keywords** + **trigger** (instruction + pattern terms); body only if refined_body_max_chars > 0 |
| **Payload in vector store** | Same | `folder`, `name`, `description` (metadata only; not used for search) |
| **Query at request time** | Same embedder | User message (e.g. “weather in London”) |
| **Injected into prompt** | System prompt | Full skill (name, description, body) loaded from SKILL.md for each selected folder |

**Are they enough?** Usually yes. **name** + **description** + **keywords** + **trigger** give semantic and phrase coverage; skills with a `trigger` get their pattern terms embedded so queries like "how's the weather in Beijing" match. For skills without keywords/trigger, add **keywords** or a **trigger** in SKILL.md; optionally set **refined_body_max_chars** > 0 at sync to include a body snippet. **Restart Core** after changing SKILL.md to re-sync.
