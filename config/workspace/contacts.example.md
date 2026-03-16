# Contacts (example for send_email flow)

Place a copy of this file at **share/contacts.md** (in your homeclaw sandbox) so the send_email DAG can resolve names to email addresses. The flow reads this file, then the LLM composes a draft using the list below.

Format: one contact per line or in a list. Include name and email; optional notes.

- **Alice** — alice@example.com
- **Bob** — bob@example.com
- **John Smith** — john.smith@company.com (work)

You can use Markdown lists or plain lines. The LLM will match the user's request (e.g. "send to John") to the right email.
