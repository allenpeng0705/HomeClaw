---
id: identity_capabilities
display_name: Assistant identity and capabilities
enabled: true
priority: 44
classifier_description: "User asks who the assistant is, what it can do, its features, or to introduce itself — onboarding / meta about the bot (你是谁, what can you do, capabilities)."

category_tools:
  profile: minimal
---

## Description
The user wants **meta information about the assistant**: identity, **what tools or skills are available**, how to use HomeClaw, *你是谁*, *你能做什么*, *有什么功能*, *介绍一下你自己*. The main answer still comes from the **LLM**, with **IDENTITY.md** and **TOOLS.md** already in the system prompt from the workspace (same as other turns). This category **narrows tools** to **minimal** so the model answers in natural language instead of reaching for unrelated tools.

## Positive examples
- “What can you do?” / “What can you do for me?”
- “你是谁？” “介绍一下你自己。”
- “你有什么功能？” “你能帮我做什么？”
- “How do I use skills in this assistant?”
- “What tools do you have access to?”
- “你的能力边界是什么？有哪些限制？”
- “第一次用你，先告诉我你能做哪些事。”

## Negative boundaries
- **general_chat**: **Brainstorming, opinions, tutoring**, or chit-chat **not** about the assistant’s identity or product capabilities — prefer **general_chat**.
- **search_web**: User wants **external** facts on the web, not “what you can do.”
- **knowledge_base** / **memory**: User wants **their KB** or **saved memory**, not the assistant’s built-in intro.

## Workflow hints
- **Minimal** tool profile; rely on workspace **IDENTITY** + **TOOLS** in context and the main LLM for the reply.
- **Semantic / hybrid routing**: This file is embedded with the other `config/intent_category/*.md` docs. With **`intent_router.mode: semantic`** or **`hybrid`**, the router can match **paraphrases** (“tell me about yourself”, “what are your limits?”) via vector similarity, not only fixed preempt phrases or the classifier LLM. After editing this file, refresh embeddings (`POST /api/intent-category/sync-vector-store` or Core startup with `refresh_on_startup`).
