---
id: general_chat
display_name: General chat and fallback
enabled: true
priority: 40
classifier_description: "Casual chat, opinions, brainstorming, conceptual explanations, greetings, or any request that does not clearly match a specialized tool category — not questions solely about who the assistant is or what it can do (use identity_capabilities)."

category_tools:
  profile: minimal
---

## Description
**Default bucket** when no specialized category clearly wins: small talk, greetings, opinions, brainstorming, “what do you think”, **high-level explanations** without a named file/URL/tool path, or **mixed/ambiguous** messages where no single action (weather, email, search, …) dominates. **Pure** “who are you / what can you do?” onboarding questions belong in **identity_capabilities**; casual “what do you think about X?” stays here.

## Positive examples
- “Hi, how are you?” / “Good morning.”
- “Explain transformers like I’m new to ML.”
- “What’s a good name for a note-taking app?”
- “I’m torn between two approaches — pros and cons?”
- “Thanks!” / follow-up chit-chat after a task.
- “你觉得这个想法靠谱吗？”
- “我们先头脑风暴几个方向，不用执行工具。”

## Negative boundaries
- **identity_capabilities**: User only wants **assistant intro / capabilities** (“what can you do?”, “你是谁”) — not general discussion.
- If the user **clearly** asks for **weather**, **stocks**, **email**, **reminders**, **KB**, **memory**, **PDF**, **slides**, **web search**, **read my file**, etc. — route to **that** category, not here.
- **coding**: They are **editing a repo**, **running commands**, or **debugging code** with concrete artifacts — prefer **coding**.
- **read_document** / **open_url**: They gave a **specific file path** or **URL** as the main object — prefer those categories.
- **search_web**: They need **current facts from the public web** (not a file they already have) — prefer **search_web**.

## Workflow hints
- **Minimal** tool profile; safe default when the router should not pre-load narrow tools.
