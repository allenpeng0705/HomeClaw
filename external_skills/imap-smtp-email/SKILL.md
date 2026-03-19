---
name: imap-smtp-email
description: Read and send email via IMAP/SMTP. Check for new/unread messages, fetch content, search mailboxes, mark as read/unread, and send emails with attachments. Works with any IMAP/SMTP server including Gmail, Outlook, 163.com, vip.163.com, 126.com, vip.126.com, 188.com, and vip.188.com.
keywords: [ "email", "send email", "发邮件", "发送邮件", "发封邮件", "邮件", "IMAP", "SMTP" ]
trigger:
  patterns:
    - "发封?邮件|发送邮件|发邮件|send\\s+email|write\\s+email|mail\\s+to"
  instruction: "User asked to send or write an email. You MUST compose a proper email from the user's intent: choose a short subject and a refined body (do not use the user's raw message as the body). Call run_skill(skill_name='imap-smtp-email', script='smtp.js', args=['send', '--to=<recipient>', '--subject=<subject>', '--body=<your composed body>']). Extract recipient from the request; body must be the actual message content you write, not the user's instruction text."
metadata:
  openclaw:
    emoji: "📧"
    requires:
      env:
        - IMAP_HOST
        - IMAP_USER
        - IMAP_PASS
        - SMTP_HOST
        - SMTP_USER
        - SMTP_PASS
      bins:
        - node
        - npm
    primaryEnv: SMTP_PASS
---

# IMAP/SMTP Email Tool

Read, search, and manage email via IMAP protocol. Send email via SMTP. Supports Gmail, Outlook, 163.com, vip.163.com, 126.com, vip.126.com, 188.com, vip.188.com, and any standard IMAP/SMTP server.

## Install dependencies

From the skill folder (e.g. `external_skills/imap-smtp-email` or `config/skills/imap-smtp-email`), run:

```bash
npm install
```

This installs `nodemailer`, `dotenv`, `imap`, and `mailparser`. Required before using the skill.

## Configuration

Variables can come from **SKILL.md** or **user input**; merge order is stable and robust (later overrides earlier):

1. **System environment** (base)
2. **SKILL.md**: frontmatter `script_env` (if present) and the **first code block below** (KEY=VALUE lines)
3. **User config**: per-skill keys from user config (e.g. user.yml)
4. **User input for this run**: optional `env` (or `script_env`) in the `run_skill` call
5. **Script `.env`**: the script also loads `.env` in the skill folder (Node `dotenv`), which can override the above

Use the code block below for defaults; put secrets in `.env` (gitignored) or user config when possible.

```bash
# IMAP Configuration (receiving email)
IMAP_HOST=imap.gmail.com          # Server hostname
IMAP_PORT=993                     # Server port
IMAP_USER=shileipeng@email.com
IMAP_PASS=
IMAP_TLS=true                     # Use TLS/SSL connection
IMAP_REJECT_UNAUTHORIZED=true     # Set to false for self-signed certs
IMAP_MAILBOX=INBOX                # Default mailbox

# SMTP Configuration (sending email)
SMTP_HOST=smtp.gmail.com          # SMTP server hostname
SMTP_PORT=587                     # SMTP port (587 for STARTTLS, 465 for SSL)
SMTP_SECURE=false                 # true for SSL (465), false for STARTTLS (587)
SMTP_USER=shileipeng@gmail.com          # Your email address
SMTP_PASS=imcugopfstgvffzv          # Your password or app password
SMTP_FROM=shileipeng@gmail.com          # Default sender email (optional)
SMTP_REJECT_UNAUTHORIZED=true     # Set to false for self-signed certs
```

## Common Email Servers

| Provider | IMAP Host | IMAP Port | SMTP Host | SMTP Port |
|----------|-----------|-----------|-----------|-----------|
| 163.com | imap.163.com | 993 | smtp.163.com | 465 |
| vip.163.com | imap.vip.163.com | 993 | smtp.vip.163.com | 465 |
| 126.com | imap.126.com | 993 | smtp.126.com | 465 |
| vip.126.com | imap.vip.126.com | 993 | smtp.vip.126.com | 465 |
| 188.com | imap.188.com | 993 | smtp.188.com | 465 |
| vip.188.com | imap.vip.188.com | 993 | smtp.vip.188.com | 465 |
| yeah.net | imap.yeah.net | 993 | smtp.yeah.net | 465 |
| Gmail | imap.gmail.com | 993 | smtp.gmail.com | 587 |
| Outlook | outlook.office365.com | 993 | smtp.office365.com | 587 |
| QQ Mail | imap.qq.com | 993 | smtp.qq.com | 587 |

**Important for Gmail:**
- Gmail does **not** accept your regular account password
- You must generate an **App Password**: https://myaccount.google.com/apppasswords
- Use the generated 16-character App Password as `IMAP_PASS` / `SMTP_PASS`
- Requires Google Account with 2-Step Verification enabled

**Important for 163.com:**
- Use **authorization code** (授权码), not account password
- Enable IMAP/SMTP in web settings first

## IMAP Commands (Receiving Email)

### check
Check for new/unread emails.

```bash
node scripts/imap.js check [--limit 10] [--mailbox INBOX] [--recent 2h]
```

Options:
- `--limit <n>`: Max results (default: 10)
- `--mailbox <name>`: Mailbox to check (default: INBOX)
- `--recent <time>`: Only show emails from last X time (e.g., 30m, 2h, 7d)

### fetch
Fetch full email content by UID.

```bash
node scripts/imap.js fetch <uid> [--mailbox INBOX]
```

### download
Download all attachments from an email, or a specific attachment.

```bash
node scripts/imap.js download <uid> [--mailbox INBOX] [--dir <path>] [--file <filename>]
```

Options:
- `--mailbox <name>`: Mailbox (default: INBOX)
- `--dir <path>`: Output directory (default: current directory)
- `--file <filename>`: Download only the specified attachment (default: download all)

### search
Search emails with filters.

```bash
node scripts/imap.js search [options]

Options:
  --unseen           Only unread messages
  --seen             Only read messages
  --from <email>     From address contains
  --subject <text>   Subject contains
  --recent <time>    From last X time (e.g., 30m, 2h, 7d)
  --since <date>     After date (YYYY-MM-DD)
  --before <date>    Before date (YYYY-MM-DD)
  --limit <n>        Max results (default: 20)
  --mailbox <name>   Mailbox to search (default: INBOX)
```

### mark-read / mark-unread
Mark message(s) as read or unread.

```bash
node scripts/imap.js mark-read <uid> [uid2 uid3...]
node scripts/imap.js mark-unread <uid> [uid2 uid3...]
```

### list-mailboxes
List all available mailboxes/folders.

```bash
node scripts/imap.js list-mailboxes
```

## SMTP Commands (Sending Email)

### send
Send email via SMTP.

```bash
node scripts/smtp.js send --to <email> --subject <text> [options]
```

**Required:**
- `--to <email>`: Recipient (comma-separated for multiple)
- `--subject <text>`: Email subject, or `--subject-file <file>`

**Optional:**
- `--body <text>`: Plain text body
- `--html`: Send body as HTML
- `--body-file <file>`: Read body from file
- `--html-file <file>`: Read HTML from file
- `--cc <email>`: CC recipients
- `--bcc <email>`: BCC recipients
- `--attach <file>`: Attachments (comma-separated)
- `--from <email>`: Override default sender

**Important:** When the user asks to send an email, compose a **refined subject and body** from their intent (e.g. "告诉他 homeclaw 可以发邮件了" → subject like "HomeClaw 功能更新", body like "你好，HomeClaw 现在可以发邮件了，特此告知。"). Do not pass the user's raw sentence as the body.

**Examples:**
```bash
# Simple text email (body = the actual message content, not the user's instruction)
node scripts/smtp.js send --to recipient@example.com --subject "Hello" --body "World"

# HTML email
node scripts/smtp.js send --to recipient@example.com --subject "Newsletter" --html --body "<h1>Welcome</h1>"

# Email with attachment
node scripts/smtp.js send --to recipient@example.com --subject "Report" --body "Please find attached" --attach report.pdf

# Multiple recipients
node scripts/smtp.js send --to "a@example.com,b@example.com" --cc "c@example.com" --subject "Update" --body "Team update"
```

### test
Test SMTP connection by sending a test email to yourself.

```bash
node scripts/smtp.js test
```

## Dependencies

```bash
npm install
```

## Security Notes

- Store credentials in `.env` (add to `.gitignore`)
- **Gmail**: regular password is rejected — generate an App Password at https://myaccount.google.com/apppasswords
- For 163.com: use authorization code (授权码), not account password

## Troubleshooting

**Connection timeout:**
- Verify server is running and accessible
- Check host/port configuration

**Authentication failed:**
- Verify username (usually full email address)
- Check password is correct
- For 163.com: use authorization code, not account password
- For Gmail: regular password won't work — generate an App Password at https://myaccount.google.com/apppasswords

**TLS/SSL errors:**
- Match `IMAP_TLS`/`SMTP_SECURE` setting to server requirements
- For self-signed certs: set `IMAP_REJECT_UNAUTHORIZED=false` or `SMTP_REJECT_UNAUTHORIZED=false`
