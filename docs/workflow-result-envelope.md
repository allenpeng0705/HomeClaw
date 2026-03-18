# Workflow result envelope (need_input / need_confirmation)

Tools that need **multi-step input** or **user confirmation** can return a standardized JSON envelope so Core pauses and resumes the flow when the user replies.

---

## Result shapes

A tool can return a **string** that is valid JSON with one of:

| `workflow_status` | Meaning |
|-------------------|--------|
| **`need_input`** | Tool needs more data (e.g. "To whom should I send?"). Core stores state and returns the `message` to the user; on the next message it merges the reply into the first `missing_fields` entry and re-calls `resume_tool`. |
| **`need_confirmation`** | Tool is waiting for confirmation (e.g. "Reply **confirm** to send"). Core stores state and returns the `message`; when the user replies with a confirm phrase (e.g. "confirm", "确认", "send"), Core calls `confirm_tool` with `confirm_args` and returns the result. |
| **`done`** | Final result (optional; plain text is also treated as done). |

---

## need_input

- **`message`** — Shown to the user (e.g. "To whom should I send this email?").
- **`resume_tool`** — Tool name to call when the user replies (e.g. `"send_email"`).
- **`resume_args`** — Arguments to pass; the first entry in **`missing_fields`** will be set to the user's reply.
- **`missing_fields`** — List of parameter names still needed (e.g. `["to"]`). Only the **first** is filled from the next user message.

Example (tool return value):

```json
{
  "workflow_status": "need_input",
  "message": "To whom should I send this email?",
  "resume_tool": "send_email",
  "resume_args": { "subject": "Hello", "body": "Hi there." },
  "missing_fields": ["to"]
}
```

Core stores this, returns `message` to the user, and on the next message calls `send_email` with `resume_args` plus `to: <user reply>`.

---

## need_confirmation

- **`message`** — Shown to the user (e.g. "I'll send this in 3 minutes. Reply **confirm** to schedule.").
- **`confirm_tool`** — Tool to run when the user confirms (e.g. `"schedule_delayed_action_confirm"`).
- **`confirm_args`** — Arguments for that tool (e.g. `{ "action_id": "..." }`).

Example:

```json
{
  "workflow_status": "need_confirmation",
  "message": "I'll run this in 5 minutes. Reply **confirm** (or 确认) to schedule, or **cancel** to discard.",
  "confirm_tool": "my_confirm_tool",
  "confirm_args": { "action_id": "abc123" }
}
```

When the user replies with a confirm phrase, Core calls `confirm_tool` with `confirm_args` and returns the tool result.

---

## Implementation notes

- Envelope is parsed in Core after each tool execution (`core/workflow_result.parse_workflow_result`). If the tool return string is JSON with `workflow_status` in `need_input` / `need_confirmation`, Core stores it in **pending workflow** (per app_id / user_id / session_id) and uses **`message`** as the reply.
- On the **next** user message, Core checks for a pending workflow before the normal LLM flow: **need_input** → merge user reply into the first missing field, re-call **resume_tool**; **need_confirmation** → if the user said confirm, call **confirm_tool** with **confirm_args**, then clear and return.
- Helpers in `core/workflow_result.py`: `build_need_input(...)`, `build_need_confirmation(...)`, `is_confirm_reply(text)`.
- Existing flows (e.g. **schedule_delayed_action** + TAM `get_pending_confirmation_for_user`) remain as-is. New or migrated flows (e.g. email compose, booking) can use this envelope so every channel gets the same follow-up and confirmation behavior.
