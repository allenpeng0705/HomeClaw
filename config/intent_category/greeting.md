---
id: greeting
display_name: Short greetings and thanks
enabled: true
priority: 60
classifier_description: "Very short social turns like hello/hi/thanks with no task request."

category_tools:
  profile: minimal
---

## Description
The user only says a short greeting or thanks with no concrete task, file, URL, or tool request. This should stay lightweight and not trigger planning, search, or coding routes.

## Positive examples
- "你好"
- "hi"
- "hello"
- "谢谢"
- "thanks"
- "哈喽"

## Negative boundaries
- **identity_capabilities**: "你能做什么" / "what can you do for me?" asks for capabilities, not pure greeting.
- **general_chat**: Non-trivial discussion or opinions beyond short social exchanges.
- **search_web** / **coding** / others: Any explicit action request should not be routed here.

## Workflow hints
- Prefer direct short text reply. No tool usage needed.
