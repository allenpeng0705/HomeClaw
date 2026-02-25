---
name: meta-social
description: |
  Post to a Facebook Page and to Instagram (Business/Creator) via Meta Graph API. Use when the user wants to post to Facebook or Instagram and you have META_ACCESS_TOKEN (Page access token) and the Page ID set.
compatibility: Requires network access and META_ACCESS_TOKEN (Page access token from developers.facebook.com; Page must have pages_manage_posts; for Instagram, link IG Business account to the Page)
trigger:
  patterns: ["post to facebook|facebook.*post|post to (instagram|ig)|instagram.*post|meta graph|facebook page|instagram.*publish|发.*facebook|发.*ins|发.*脸书|发.*instagram"]
  instruction: "User asked to post to Facebook or Instagram. Use run_skill(skill_name='meta-social-1.0.0', script='request.py', args=[...]). Requires META_ACCESS_TOKEN and page_id. Do not say you have no skill."
---

# Meta Social (Facebook Page + Instagram)

Post to a **Facebook Page** and to **Instagram** (Business/Creator accounts) using the [Meta Graph API](https://developers.facebook.com/docs/graph-api). **Free** — create an app at [developers.facebook.com](https://developers.facebook.com), get a Page access token with `pages_manage_posts` (and for Instagram: link an Instagram Business account to the Page and use `instagram_business_content_publish`).

## How users ask

- "Post to my Facebook Page: Hello everyone"
- "Post this to Facebook: …"
- "Post to Instagram: [image URL] with caption …"
- "Publish this image to Instagram: …"

## run_skill (recommended)

**Facebook Page — post text:**
- **run_skill**(skill_name=`meta-social-1.0.0`, script=`request.py`, args=[`facebook`, `post`, `<page_id>`, `Your message here`])
- `page_id`: numeric Facebook Page ID (from Page settings or Graph API).

**Instagram — post image (with optional caption):**
- **run_skill**(skill_name=`meta-social-1.0.0`, script=`request.py`, args=[`instagram`, `post`, `<page_id>`, `<image_url>`, `Optional caption`])
- Image must be **publicly accessible URL** (JPEG). Page must have an Instagram Business account linked.

## Base URL

```
https://graph.facebook.com/v21.0
```

## Authentication

- **Page access token:** Set `META_ACCESS_TOKEN` in the environment where Core runs, or set `meta_access_token` in this skill's `config.yml` (env overrides config).
- Get the token from [developers.facebook.com](https://developers.facebook.com): create an app, add Facebook Login and request Page permissions (`pages_manage_posts`); for Instagram also request `instagram_business_content_publish` and link an IG Business account to the Page. Use the Graph API Explorer or your app flow to obtain a Page access token.

## Endpoints (used by request.py)

| Platform  | Action      | Method | Path / flow |
|-----------|-------------|--------|-------------|
| Facebook  | Post to Page| POST   | `/{page-id}/feed` — body `message` |
| Instagram | Post image  | POST   | 1) `/{page-id}?fields=instagram_business_account` → get IG user id; 2) POST `/{ig-user-id}/media` (image_url, caption) → container id; 3) POST `/{ig-user-id}/media_publish` (creation_id) |

## Errors and rate limits

- **401 / 190:** Invalid or expired token — re-authorize and get a new Page token.
- **403:** Permission denied — ensure Page role and app permissions (e.g. `pages_manage_posts`, `instagram_business_content_publish`).
- **100:** Instagram: Page has no linked Instagram Business account — connect IG in Page settings.
- **429:** Rate limit — Instagram allows ~50 posts per 24h per account.

## Links

- [Page Feed (Graph API)](https://developers.facebook.com/docs/graph-api/reference/page/feed/)
- [Instagram Content Publishing](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/content-publishing/)
- [Graph API Explorer](https://developers.facebook.com/tools/explorer/)
