---
name: x-api
description: |
  Post tweets and read timeline via X (Twitter) API v2. Use when the user wants to post a tweet or read their X timeline and you have X_ACCESS_TOKEN (or x_access_token in config) set.
compatibility: Requires network access and X_ACCESS_TOKEN (OAuth 2.0 user access token from developer.x.com)
trigger:
  patterns: ["post.*tweet|tweet.*post|post to (x|twitter)|x\\.com.*post|twitter api|X API"]
  instruction: "User asked to post a tweet or use X (Twitter) API. Use run_skill with script request.py: post <text> to create a tweet, or get [max_results] to read timeline. Requires X_ACCESS_TOKEN (OAuth 2.0 user token from developer.x.com)."
---

# X (Twitter) API v2

Post tweets and read your timeline using the official [X API v2](https://developer.x.com/en/docs/twitter-api). **Free tier** available (developer account + app at [developer.x.com](https://developer.x.com)). You provide a user access token (OAuth 2.0 PKCE or OAuth 1.0a); the skill calls the API on your behalf.

## How users ask

- "Post a tweet: Hello world"
- "Tweet this: …"
- "Post to X: …"
- "What are my latest tweets?" / "Read my X timeline"

## run_skill (recommended)

**Post a tweet:**
- **run_skill**(skill_name=`x-api-1.0.0`, script=`request.py`, args=[`post`, `Hello world`])
- Text is the second argument; keep under 280 characters.

**Read timeline:**
- **run_skill**(skill_name=`x-api-1.0.0`, script=`request.py`, args=[`get`, `10`])
- Second arg optional: max_results (default 10, max 100).

## Base URL

```
https://api.twitter.com/2
```

## Authentication

- **User access token:** Set `X_ACCESS_TOKEN` in the environment where Core runs, or set `x_access_token` in this skill's `config.yml` (env overrides config).
- Get the token from [developer.x.com](https://developer.x.com): create a Project and App, then complete OAuth 2.0 Authorization Code with PKCE (or OAuth 1.0a) to obtain a user access token. Use that token as the Bearer token for API requests.

## Endpoints (used by request.py)

| Action       | Method | Path                 | Body / notes                    |
|--------------|--------|----------------------|---------------------------------|
| Post tweet   | POST   | `/tweets`            | `{"text": "Your tweet text"}`   |
| User timeline| GET    | `/users/:id/tweets`  | Script resolves id via `/users/me`; query max_results (default 10) |

## Errors and rate limits

- **401:** Invalid or expired token — re-authorize at developer.x.com.
- **403:** Forbidden (e.g. app not allowed to post) — check app permissions.
- **429:** Rate limit — wait and retry. Free tier has limited requests per 15 min.

## Links

- [X API v2 – Manage Tweets](https://developer.x.com/en/docs/twitter-api/tweets/manage-tweets/api-reference/post-tweets)
- [Authentication (OAuth 2.0)](https://developer.x.com/en/docs/authentication/oauth-2-0)
- [Developer Portal](https://developer.x.com)
