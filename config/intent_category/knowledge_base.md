---
id: knowledge_base
display_name: Knowledge base (KB)
enabled: true
priority: 52
classifier_description: "Search, add, list, or remove entries in the structured knowledge base (KB / 知识库) — not informal 'remember this' chat memory."

category_tools:
  tools:
  - knowledge_base_search
  - knowledge_base_add
  - knowledge_base_remove
  - knowledge_base_list
---

## Description
The user wants **KB CRUD and search**: organizational or curated knowledge stored in the **knowledge base** product — *知识库*, *KB*, *存一条*, *检索知识库*, onboarding runbooks, API conventions, **not** the same as casual “remember my dog’s name” (**memory**). They may **search**, **append**, **delete stale entries**, or **list** what exists.

## Positive examples
- “Search the KB for deployment steps.”
- “Add to knowledge base: staging API is `https://…`.”
- “知识库里关于 OnCall 的文档有哪些？”
- “Remove the outdated VPN entry from KB.”
- “List all KB entries tagged billing.”
- “把这段规范加入知识库并标记为安全策略。”
- “在知识库里检索‘报销流程’并给我摘要。”

## Negative boundaries
- **memory**: Informal **remember / recall** without KB framing — preferences, past chat, “what did I say” — **memory** tools.
- **search_web**: **Public internet**, not the private KB index.
- **read_document**: User gave a **file path** in the workspace, not “search KB”.
- **general_chat**: Discussing “we should have a wiki” **without** asking to query or edit KB — chat.

## Workflow hints
- `knowledge_base_search`, `knowledge_base_add`, `knowledge_base_remove`, `knowledge_base_list` per intent.
