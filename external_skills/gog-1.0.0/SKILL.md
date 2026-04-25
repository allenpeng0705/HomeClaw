---
name: gog
description: Google Workspace CLI for Gmail, Calendar, Drive, Contacts, Sheets, and Docs via gog CLI.
homepage: https://gogcli.sh
trigger:
  patterns:
    - "gog\\s+(gmail|calendar|drive|contacts|sheets|docs|auth)"
    - "gog\\s+(send|search|list|events|cat|get|update|export)"
    - "gmail\\s+(search|send|list)"
    - "google\\s+(calendar|sheets|drive|docs)"
    - "(google\\s+)?workspace"
  instruction: |
    The user asked about Gmail, Google Calendar, Drive, Sheets, Docs, or Contacts via gog.
    Use run_skill with the appropriate subcommand args:
      args=["gmail", "--search", "<query>", "--max", "10"]
      args=["gmail", "--to", "<email>", "--subject", "<subject>", "--body", "<body>"]
      args=["calendar", "--list-events", "--from", "<iso>", "--to", "<iso>"]
      args=["drive", "--search", "<query>", "--max", "10"]
      args=["contacts", "--list", "--max", "20"]
      args=["sheets", "--get", "<sheetId>", "<range>", "--json"]
      args=["sheets", "--update", "<sheetId>", "<range>", "--values-json", "<json>"]
      args=["docs", "--cat", "<docId>"]
      args=["auth", "--status"]
    For any gog subcommand, use args=["raw", "<subcommand>", ...args] as fallback.
    Requires OAuth setup: gog auth credentials + gog auth add.
---

# gog

Use `gog` for Gmail/Calendar/Drive/Contacts/Sheets/Docs. Requires OAuth setup.

## Setup (once)

```bash
gog auth credentials /path/to/client_secret.json
gog auth add you@gmail.com --services gmail,calendar,drive,contacts,sheets,docs
gog auth list
```

## run_skill commands

| Task | Args |
|------|------|
| Search Gmail | `["gmail", "--search", "<gmail-query>", "--max", "10"]` |
| Send email | `["gmail", "--to", "<email>", "--subject", "<sub>", "--body", "<body>"]` |
| List calendar events | `["calendar", "--list-events", "--from", "<iso>", "--to", "<iso>"]` |
| Search Drive | `["drive", "--search", "<query>", "--max", "10"]` |
| List contacts | `["contacts", "--list", "--max", "20"]` |
| Read Sheets range | `["sheets", "--get", "<sheetId>", "<range>", "--json"]` |
| Update Sheets range | `["sheets", "--update", "<sheetId>", "<range>", "--values-json", "<json>"]` |
| Read Docs | `["docs", "--cat", "<docId>"]` |
| Auth status | `["auth", "--status"]` |
| Raw gog command | `["raw", "<subcommand>", ...args]` |

## Notes

- Set `GOG_ACCOUNT=you@gmail.com` to avoid repeating `--account`.
- For scripting, prefer `--json` where available.
- Confirm before sending mail or creating events.
- In-place Docs edits require a Docs API client (not in gog).
