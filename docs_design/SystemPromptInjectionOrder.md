# System prompt injection order and force-include design

This document describes the **canonical order** of system prompt sections in `answer_from_memory` (core/core.py) and the design of **skills_force_include_rules** / **plugins_force_include_rules**, so we can reason about impact and keep injection consistent.

---

## 0. Tools vs skills (and what “no tool_calls” means)

- **Tools** are the callable actions the model can use: `run_skill`, `file_read`, `time`, `route_to_plugin`, `memory_search`, etc. They are registered in the tool registry and appear in the “tools” list sent to the LLM.
- **Skills** are not a separate layer. A skill is invoked **via the `run_skill` tool**: the model calls `run_skill(skill_name="image-generation-1.0.0", script="generate_image.py", args=[...])`. So “run a skill” = “call the run_skill tool with that skill’s folder and script.”
- **“No tool_calls”** means the model returned a **text reply without calling any tool** — no run_skill, no file_read, no route_to_plugin, etc. So it’s “no tools and no skills” in one: the model chose to answer with text only.
- **Force-include** only affects **which skills are listed** in the system prompt (and optionally adds an instruction or auto_invoke). It does not add new tools; `run_skill` is already a tool. The model is still expected to call `run_skill` when the user asks for something that matches a skill. When the model doesn’t call it (returns text like “no image tool”), **auto_invoke** can run `run_skill` as a fallback — but we only do that when the model’s reply looks unhelpful (see §2), so we don’t run it when the user asked “how?” and the model gave a helpful explanation.

---

## 1. Canonical system prompt order

The system message is built as `"\n".join(system_parts)`. Sections are appended in this order:

| Order | Section | When | Purpose |
|-------|---------|------|--------|
| 1 | Workspace bootstrap | `use_workspace_bootstrap` | Identity, AGENTS.md, TOOLS.md (optional). |
| 2 | Agent memory directive or content | `use_agent_memory_search` or `use_agent_memory_file` | Either “use agent_memory_search / agent_memory_get” or inject AGENT_MEMORY.md + optional daily memory. |
| 3 | **Available skills** | `use_skills` | Skills (vector-retrieved or first N) + “call run_skill(skill_name=…)”; see Design §3.6. |
| 4 | **RAG memory** | `use_memory` | `_fetch_relevant_memories(query)` → “Here is the given context: …”. |
| 5 | Knowledge base | `knowledge_base` enabled + user | Chunks from Cognee/Chroma for saved docs. |
| 6 | About the user | `profile.enabled` + user | Profile store snippet. |
| 7 | Main prompt | prompt_manager or RESPONSE_TEMPLATE | “Chat/response” template (how to respond). |
| 8 | Response language and format | `main_llm_language` | “Respond only in …; output only your direct reply …”. |
| 9 | **Routing block** | `unified` + plugin_manager | “## Routing (choose one)” + available plugins + run_skill/route_to_plugin/remind_me/etc. |
| 10 | Recorded events (TAM) | orchestratorInst.tam | Upcoming events from record_date. |
| 11 | **Instruction for this request** | When a force-include rule matches | Optional per-request instruction from `skills_force_include_rules` / `plugins_force_include_rules`. |

Then: `llm_input = [{"role": "system", "content": "\n".join(system_parts)}]` and `llm_input += messages` (conversation).

So **identity and context** come first (workspace, memory, skills, RAG, KB, profile), then **how to respond** (main prompt, language, routing), then **TAM**, then **request-specific instruction** (force-include) at the very end.

---

## 2. Force-include rules (skills and plugins)

**Config:** `skills_force_include_rules` and `plugins_force_include_rules` in core.yml. Each rule has:

- **pattern:** Regex matched against the user query (case-insensitive).
- **folders** (skills) or **plugins** (plugins): List of skill folder names or plugin ids to ensure are in the prompt.
- **instruction** (optional): String appended as “## Instruction for this request” when the rule matches.

**Behavior:**

- When the user message matches a rule’s pattern, Core adds the listed skills/plugins to the injected list (and trims to `skills_max_in_prompt` / `plugins_max_in_prompt`).
- If the rule has `instruction`, that text is collected and later appended to `system_parts` in one place (see §3).

So **selection** (which skills/plugins appear) is contextual; **instruction** placement is global (one block at the end, for all matched rules).

**auto_invoke (optional):** When the model returns **no tool_calls**, Core can run a tool (e.g. run_skill) from the rule so the skill runs anyway. We only run it when the model's reply looks **unhelpful** (short or contains "no tool" / "not available") so we don't run it when the user asked "how?" and the model gave a helpful explanation. Use `{{query}}` in arguments to substitute the user message.

---

## 3. Where “Instruction for this request” is placed

**Current implementation:** All force-include instructions are appended **at the end** of the system prompt (after TAM, before the conversation).

**Rationale:**

- Many models pay more attention to the **end** of the system message. Putting the instruction last maximizes the chance the model will call the tool (e.g. run_skill) instead of replying with “no tool available.”
- The heading “Instruction for this request” and the wording in config (“For this request only …”) scope it to the current turn.

**Tradeoffs:**

| Placement | Pros | Cons |
|-----------|------|------|
| **End of system (current)** | Strong recency; better compliance for “call run_skill first.” | Can be seen as overriding earlier guidelines (e.g. “respond only in language X”) if the instruction is read as “do this instead of everything above.” In practice we phrase it as “call run_skill first” so the model still follows language/format for the final reply. |
| **Right after “Available skills” / “Routing”** | Contextual (instruction next to the skill or plugin list). | A lot of content (memory, KB, profile, main prompt, routing) comes after; the model may “forget” the instruction. We tried this and saw the model still reply “no image tool.” |
| **Prepend to first user message** | Clearly turn-specific. | Would require changing message shape (synthetic user message or extra system message); not done today. |

**Conclusion:** Keeping the instruction at the **end** of the system prompt is a reasonable default for tool-use compliance. To avoid overriding general guidelines:

- Keep force-include instructions **narrow**: “Call run_skill … for this request” rather than broad “Ignore all other instructions.”
- In config, phrase instructions so they add a **requirement** (e.g. “You MUST call run_skill first”) without contradicting “Respond only in …” or “Output only your direct reply.”

If we need to support deployments that prefer contextual placement, we can add a config knob later (e.g. `skills_force_include_instruction_position: end_of_system | after_skills`) and default to `end_of_system`.

---

## 4. Impact on other behaviors

- **RAG, KB, profile:** Unchanged. They are injected before the main prompt and routing; force-include does not remove or reorder them.
- **Main prompt and “Response language and format”:** Still in the same place. The force-include block is additive (“for this request, also do X first”); we do not strip or replace earlier sections.
- **Routing block:** Unchanged. Plugins force-include only adds plugin ids to the list and optionally adds an instruction at the end; the routing text itself is unchanged.
- **Compaction:** If compaction is enabled, it trims **messages** (conversation), not the system message. So the full system prompt (including force-include instruction) is always sent.
- **Tool loop:** The model still gets the same tools; we only added a strong hint to use run_skill when the query matches a rule. So other tools (memory_search, file_read, etc.) are unaffected.

**Summary:** Injection order is explicit and documented; force-include only **adds** a section at the end and **adds** skills/plugins to the existing lists. It does not reorder or remove other sections, so other behaviors remain as before. The only deliberate override is “for this request, call this tool first,” which is scoped by the heading and config text.

---

## 5. Reference: config and code

- **Config:** `config/core.yml` → `skills_force_include_rules`, `plugins_force_include_rules`. See `config/core.yml.reference` for schema and examples.
- **Code:** `core/core.py` → `answer_from_memory`: `system_parts` built in the order above; `force_include_instructions` collected from rules and appended at the end before `llm_input`.
- **Design:** Skills §3.6, SessionAndDualMemoryDesign (order: workspace → agent memory → RAG → guidelines); this doc extends that with the full list and force-include semantics.
