---
id: memory
display_name: Agent or session memory
enabled: true
priority: 51
classifier_description: "Remember, recall, or search conversational or agent memory — preferences, past facts, 'what did I say', daily notes — not the formal knowledge base."

category_tools:
  tools:
  - memory_search
  - memory_get
  - agent_memory_search
  - agent_memory_get
  - append_agent_memory
  - append_daily_memory
---

## Description
The user wants **personal or session-persistent memory**: save a preference, recall prior context, *记住*, *之前说过*, *我的习惯*, append daily log, search what the agent stored about them. This is **lightweight recall**, distinct from **knowledge_base** (structured KB / 知识库 operations).

## Positive examples
- “Remember my timezone is Asia/Shanghai.”
- “What did I tell you about my printer last week?”
- “搜索一下你记下的项目笔记”
- “Append to daily memory: released v2 today.”
- “Forget the old WiFi SSID you stored.”
- “What’s my default editor preference you saved?”
- “记住我喜欢用中文回复。”
- “把今天会议结论写进每日记忆。”

## Negative boundaries
- **knowledge_base**: User says **知识库**, **KB**, or formal add/search/remove of **org wiki** entries.
- **search_web**: **Public** facts (“capital of …”), not “what I told you”.
- **read_document**: User references a **file path**, not “what you remember”.
- **schedule_remind**: They want a **timed reminder** — **schedule_remind**, not storing a free-form fact (unless both — pick primary verb).

## Workflow hints
- `memory_*`, `agent_memory_*`, `append_*_memory` as configured in Core.
