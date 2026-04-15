---
id: send_email
display_name: Send email
enabled: true
priority: 52
classifier_description: "Compose or send email via SMTP — recipient, subject, body, attachments — 发邮件, 写邮件, mailto workflow with confirmation."

category_tools:
  tools:
  - file_read
  - run_skill
  skills:
  - imap-smtp-email
---

## Description
The user wants to **send email**: draft a message, attach a file, *发邮件给*, *写邮件*, forward content by mail, **SMTP send** with the usual **confirm before send** flow. Distinct from posting in chat, saving a file only, or **reminders** without mail (**schedule_remind**).

## Positive examples
- “Email the summary to `alice@example.com`.”
- “帮我发一封邮件给老板，说明延期原因”
- “Send `report.pdf` as an attachment to the team list.”
- “Draft a polite follow-up — I’ll approve before send.”
- “Reply-all to the thread with this paragraph.”
- “给客户发邮件，附件是 output/proposal.pdf。”
- “先帮我起草邮件，确认后再发。”

## Negative boundaries
- **general_chat**: **Talking about** email etiquette — no send action.
- **read_document**: Only **reading** a file — no **mail** verb.
- **schedule_remind**: **Remind me later** — not “email someone” (unless they explicitly want both — prefer the **dominant** action).
- **get_file_link**: **Link only** — no email — unless they then say “email that link” (**send_email**).

## Workflow hints
- `run_skill(imap-smtp-email)`; `file_read` for attachment bodies; respect confirmation policy in skill.
