---
name: hootsuite
description: |
  Post or schedule to X, Facebook, LinkedIn, and Instagram via Hootsuite. Use when the user has a Hootsuite account and wants to post/schedule to connected social profiles; requires HOOTSUITE_ACCESS_TOKEN.
compatibility: Requires network access, Hootsuite subscription, and HOOTSUITE_ACCESS_TOKEN (OAuth 2.0 access token from developer.hootsuite.com)
trigger:
  patterns: ["hootsuite|post via hootsuite|schedule.*hootsuite|hootsuite.*post|hootsuite.*schedule"]
  instruction: "User asked to use Hootsuite to post or schedule. Use run_skill with script request.py: list (get profile IDs), or post <profile_id> <text> [scheduledSendTime]. Requires HOOTSUITE_ACCESS_TOKEN."
---

# Hootsuite (multi-platform post/schedule)

Post or schedule to **X (Twitter), Facebook, LinkedIn, Instagram** (and Pinterest) through the [Hootsuite Publishing API](https://developer.hootsuite.com/docs/api-overview). **One OAuth token** — post to any connected social profile. Requires a **Hootsuite subscription** and an app/access token from [developer.hootsuite.com](https://developer.hootsuite.com).

Use this skill if you already pay for Hootsuite; otherwise prefer **x-api-1.0.0** (X) and **meta-social-1.0.0** (Facebook + Instagram) for free official APIs.

## How users ask

- "Post to X and Facebook via Hootsuite: Hello world"
- "Schedule a Hootsuite post for 3pm tomorrow: …"
- "What are my Hootsuite social profiles?"
- "Post to my Hootsuite LinkedIn profile: …"

## run_skill (recommended)

**List social profiles** (get IDs for posting):
- **run_skill**(skill_name=`hootsuite-1.0.0`, script=`request.py`, args=[`list`])

**Post or schedule:**
- **run_skill**(skill_name=`hootsuite-1.0.0`, script=`request.py`, args=[`post`, `<profile_id>`, `Your message text`])
- To schedule: add a 4th arg — ISO-8601 UTC time, e.g. `2025-02-20T15:00:00Z` (must be at least 5 minutes in the future). If omitted, message is scheduled 5 minutes from now.

Multiple profiles: **run_skill**(..., args=[`post`, `id1,id2`, `text`]) — comma-separated profile IDs.

## Base URL

```
https://platform.hootsuite.com/v1
```

## Authentication

- **Access token:** Set `HOOTSUITE_ACCESS_TOKEN` in the environment where Core runs, or set `hootsuite_access_token` in this skill's `config.yml` (env overrides config).
- Get the token via [OAuth 2.0](https://developer.hootsuite.com/docs/api-authentication) (Authorization Code or member_app) at [developer.hootsuite.com](https://developer.hootsuite.com).

## Endpoints (used by request.py)

| Action | Method | Path | Notes |
|--------|--------|------|-------|
| List profiles | GET | `/socialProfiles` | Returns profile IDs and types (FACEBOOK, TWITTER, LINKEDIN, INSTAGRAM, etc.) |
| Schedule message | POST | `/messages` | Body: text, socialProfileIds[], scheduledSendTime (ISO-8601 UTC, ≥5 min future) |

## Errors and rate limits

- **401:** Invalid or expired token — re-authorize via Hootsuite OAuth.
- **403:** Forbidden — check app permissions and Hootsuite plan.
- **429:** Rate limit — wait and retry.
- Scheduled time must be at least 5 minutes in the future (UTC).

## Links

- [Hootsuite API Overview](https://developer.hootsuite.com/docs/api-overview)
- [Message Scheduling](https://developer.hootsuite.com/docs/message-scheduling)
- [Authentication](https://developer.hootsuite.com/docs/api-authentication)
