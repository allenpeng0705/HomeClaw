# Tool and Skill Selection: Design and Discussion

This document summarizes how OpenClaw handles tool/skill selection and describes **HomeClaw's chosen approach: same as OpenClaw** — no config-driven intent layer; narrow the tool/skill set and rely on strong descriptions so the model picks correctly.

**Principle:** Do **not** use tables, phrase lists, or regexes for intent logic when the LLM can do it — we cannot list every phrasing, language, or edge case. Prefer the LLM (e.g. for intent routing: one short classification call) over maintaining large config tables.

---

## 1. How OpenClaw Handles Tool/Skill Selection

Findings from the OpenClaw codebase (`../openclaw-main`):

### 1.1 No intent-first layer

OpenClaw does **not** run a phrase/regex or classifier step before the LLM to map "user said X" → "use tool Y." Tool and skill choice is left to the model.

### 1.2 Narrowing the set by config

- **Skill filter (`skillFilter`)**  
  Per agent (and per channel/group/topic), config can restrict which skills are loaded: e.g. `skills: ["weather", "summarize"]`. The LLM only sees this subset. So they reduce *how many* skills the model can choose from, not *which* tool to use for a given phrase.

- **Tool profiles**  
  Core tools have profiles (`minimal`, `coding`, `messaging`, `full`). The catalog can be filtered by profile so the prompt only includes tools for that profile. Again, this is "fewer tools," not "for this intent, use this tool."

### 1.3 How the model chooses

- **Skills:** From the skill-creator SKILL.md: *"name and description are the only fields Codex reads to determine when the skill gets used."*  
  So: the model picks from the skill list using **name + description** (and whatever is in the prompt). Many skills also document "When to use" / "trigger phrases" in the **body** of SKILL.md; that's guidance for the model once the skill is in context, not an enforced mapping in code.

- **Tools:** The gateway exposes a **tools.catalog** (core tools + plugins). Descriptions and structure are fixed in code (e.g. `tool-catalog.ts`). There is no code path that says "if the user says 'search the web', only offer or force `web_search`."

### 1.4 Summary for OpenClaw

| Mechanism              | Purpose                                      |
|------------------------|----------------------------------------------|
| `skillFilter`          | Reduce number of skills per agent/channel   |
| Tool profiles          | Reduce number of tools in the prompt        |
| Skill name + description | Let the model decide when to use a skill  |
| No intent → tool map   | No phrase-based routing or forced tool      |

So OpenClaw's approach is: **smaller, context-appropriate tool/skill sets + strong descriptions**, and reliance on the model. No config-driven "when user says X, use tool Y" layer.

---

## 2. Chosen Direction: Same as OpenClaw (No Config-Driven Intent)

We do **not** want a config-driven intent → tool layer (no big table of phrases → tools in config). Instead we adopt OpenClaw's approach:

1. **Narrow the tool set** — so the LLM sees fewer tools (e.g. by profile or allowlist), reducing confusion between similar tools (exec vs web_search, tavily_crawl vs web_search).
2. **Narrow the skill set** — optional filter so only certain skills are in the prompt per agent/context (like OpenClaw's `skillFilter`).
3. **Strong tool and skill descriptions** — clear name + description for each tool and each skill (SKILL.md frontmatter + body "When to use") so the model can choose correctly from the reduced set.
4. **No phrase-based routing in config** — we do not maintain a separate intent table; we rely on the model choosing from the (smaller) set using descriptions.

Implications:

- **Remove or phase out** the config-driven force-include rules and auto_invoke fallbacks that map patterns → tools. The main mechanism is "smaller set + good descriptions," not "when user says X, run tool Y."
- **Optionally** keep a minimal safety net in code (e.g. one or two hardcoded fallbacks) only if we still see critical failures; that would be code-level, not a large config table.

---

## 3. What HomeClaw Needs to Match OpenClaw

### 3.1 Tool set narrowing

- **Option A: Tool profiles**  
  Assign each built-in tool to one or more profiles (e.g. `minimal`, `coding`, `messaging`, `full`). Config specifies which profile(s) to use (e.g. `tools.profile: full` or `tools.profiles: [minimal, messaging]`). Only tools in the selected profile(s) are passed to the LLM.

- **Option B: Allow/deny list**  
  Config lists tools to include or exclude: e.g. `tools.allow: [web_search, folder_list, document_read, run_skill, ...]` or `tools.deny: [exec]` for certain contexts. Simpler than profiles but more manual.

Recommendation: start with **profiles** (like OpenClaw) so we can ship presets (e.g. "messaging" = web_search, folder_list, run_skill, …; "full" = everything). If we need per-agent overrides, we can add an optional allow/deny on top.

### 3.2 Skill set narrowing (optional)

- **Skill filter**  
  Config option e.g. `skills_filter: [html-slides-1.0.0, ppt-generation-1.0.0]` (or per-agent in core). When set, only these skills are included in the prompt; when unset, current behavior (all skills or RAG result). This mirrors OpenClaw's `skillFilter`.

- We already have **skills_use_vector_search** (RAG reduces skills by similarity). An explicit **skills_filter** would be an alternative or complement: user picks a fixed list instead of (or in addition to) RAG.

### 3.3 Strong descriptions

- **Tools:** In `tools/builtin.py` (and any plugin tool definitions), ensure each tool has a short, unambiguous **description** that states when to use it and when not to (e.g. "Search the web. Use for any user request to search or look up something online. Do not use for crawling a specific URL — use tavily_crawl for that.").
- **Skills:** In each SKILL.md, frontmatter **name** and **description** should clearly describe when the skill is used; body can add "When to use" / trigger phrases as guidance. No need for a separate config table — the skill docs are the source of truth.

### 3.4 Remove or simplify force-include / fallbacks

- **skills_force_include_rules** with patterns + **auto_invoke** are the config-driven intent layer we are moving away from. Plan:
  - **Phase out** pattern-based rules that map "user said X" → "run tool Y" or "inject this instruction."
  - Either remove `skills_force_include_rules` entirely once tool/skill narrowing + descriptions are in place, or keep the config key only for **skill/plugin inclusion** (e.g. "also include these skill folders in the prompt") without pattern matching or auto_invoke.
- **Hardcoded fallbacks** in `llm_loop.py` (folder_list, web_search when no tool_calls, exec rejection for search) can be removed or reduced to a single minimal fallback in code if we still see a critical case; no large config table.

---

## 4. Proposed Next Steps

1. **Define tool profiles**  
   Assign each built-in tool to one or more profiles (e.g. in a small table in code or in tools config). Add config (e.g. under `tools` in `skills_and_plugins.yml`) to select profile(s). Filter the tool list in the LLM loop by selected profile(s).

2. **Add optional skill filter**  
   Config key e.g. `skills_filter: [list of skill folder names]`. When set, only those skills are loaded into the prompt (same idea as OpenClaw's skillFilter). When unset, keep current behavior (all skills or RAG).

3. **Tighten tool and skill descriptions**  
   Review and improve descriptions in `tools/builtin.py` and in SKILL.md files so that with a smaller tool set the model can reliably choose the right tool/skill.

4. **Phase out config-driven intent**  
   Remove or simplify `skills_force_include_rules` (no pattern → tool / auto_invoke). Remove or minimize hardcoded phrase-based fallbacks in `llm_loop.py`. Rely on profile filtering + skill filter + descriptions instead.

---

## 5. Summary

| Topic                 | OpenClaw                         | HomeClaw (chosen)                            |
|-----------------------|----------------------------------|---------------------------------------------|
| Intent → tool mapping | None                             | None — same as OpenClaw                     |
| Reducing set          | skillFilter, tool profiles       | skills_filter (optional), tool profiles     |
| Wrong tool            | Addressed by smaller set + descriptions | Same: fewer tools + clear descriptions   |
| Force-include / fallbacks | N/A                          | Phase out; no config-driven intent table   |

We use the **same way as OpenClaw**: no config-driven intent layer; **narrow the tool and skill set** (profiles + optional skill filter) and **strong descriptions** so the model selects the right tool/skill.
