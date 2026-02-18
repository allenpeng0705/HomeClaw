# Outbound Markdown and unknown-request notification

This doc describes two optional features: **(1) outbound Markdown conversion** so channels that don’t display Markdown well can show readable text, and **(2) notifying the owner when an unknown user tries to access** so they can add that identity to `config/user.yml` (no separate “pairing” flow).

---

## 1. Outbound Markdown (Core applies by default)

**Purpose:** When the assistant’s reply is **Markdown** (e.g. `**bold**`, `*italic*`, code blocks, lists) and the **channel cannot render Markdown** well, the user may see raw Markdown. Outbound Markdown conversion turns the reply into something the channel can display nicely.

**When we convert:** **Only when the result looks like Markdown** (e.g. contains `**`, `*`, `` ` ``, `#`, links, etc.). If the reply is plain text, Core sends the **original text** unchanged. So Markdown replies get converted; plain replies pass through as-is.

**Who does it:** **Core** converts (when applicable) **before** sending to channels. Channels receive the text and send it as-is; they do **not** need to call any Markdown helper.

**Config:** In `config/core.yml` — **`outbound_markdown_format`**: `whatsapp` (default) | `plain` | `none`

- **whatsapp** — when the reply is Markdown, convert to `*bold*` `_italic_` `~strikethrough~` (works for most IMs: WhatsApp, Telegram, Signal, etc.).
- **plain** — when the reply is Markdown, strip to **plaintext**. Use this if your channel **does not support** the whatsapp-style markers (e.g. some SMS or minimal clients); you still get readable text without raw `**` or `*`.
- **none** — no conversion; always send the raw assistant reply.

**Implementation:**

- **Core** uses a helper when building every outbound `response_data["text"]`. The helper checks `outbound_markdown_format`; if `none`, returns original text. If the text **does not look like Markdown** (no bold/italic/code/headers/links), returns original text. Otherwise converts via **base/markdown_outbound.py** (`looks_like_markdown` + `markdown_to_channel`); on any failure returns the **original text** so Core never crashes.
- **base/markdown_outbound.py** (never raises): `looks_like_markdown(text)`, `markdown_to_plain(text)`, `markdown_to_whatsapp(text)`, `markdown_to_channel(text, format)`.
- Channels just send the text they receive.

**Summary:** Conversion runs **only when the result is Markdown**; otherwise the original text is sent. Config in `core.yml`: `whatsapp` (default for most IMs) or `plain` for channels that don’t support whatsapp format (plaintext output).

---

## 2. Unknown-request notification (no separate pairing)

**What we already have:** **user.yml** is the allowlist. Each user has `im`, `email`, `phone` (channel identities). If the request’s `user_id` is not in any user’s list for that channel type, Core **denies** (401). So “pairing” in the sense of “who can access” is already done via user.yml.

**Permission rule unchanged (empty list = allow all):** The unknown-request notification **does not change** permission logic. The rule remains: **if a user’s list (`im`, `email`, or `phone`) is empty for that channel type, that user is treated as a match — i.e. allow all senders for that channel.** So empty list = allow all. We encourage users to set permission lists correctly (non-empty when you want to restrict access). Only when **no** user matches (every user has a non-empty list and the request’s `user_id` is not in any of them) do we deny — and optionally notify.

**What we may add:** An optional **notification** when an **unknown** user is **denied**:

1. **Detect:** Core receives a request; `check_permission` returns no match (deny). Notification runs **only** in this case; it never affects when we allow or deny.
2. **Notify:** Optionally send a message to the **last-used channel** (the channel that last sent a message to Core — typically the owner’s). The message says something like: *“Unknown request from \<channel_name\>: user_id=\<user_id\>. Add this identity to config/user.yml (under im, email, or phone) to allow access.”*
3. **Owner decides:** The owner sees this on their client and can **add** that identity to user.yml (im, email, or phone) and reload. No separate pairing flow.

**Config:** Optional `notify_unknown_request: true` in `config/core.yml`. When `true` and permission is **denied**, Core pushes that message to the response queue for the last-used channel. The owner gets the notification there.

**Important:** We only update “last channel” when the request is **allowed**. So when an unknown user is denied, we do **not** overwrite last channel; the notification goes to the owner’s last-used channel.

**Summary:** Permission rule is unchanged: empty list = allow all. Optional: when a request is denied (no user matched), notify the owner via last-used channel so they can add that identity to user.yml. We encourage setting permission lists correctly.
