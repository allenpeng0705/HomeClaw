# Weibo, WeChat, and Redbook (Xiaohongshu) skills — investigation

This doc investigates how to implement HomeClaw skills for **Weibo** (微博), **WeChat** (微信), and **Redbook** (小红书 / Xiaohongshu), following the same pattern as **x-api-1.0.0** and **meta-social-1.0.0** (official APIs, token in config/env, `scripts/request.py`).

---

## Summary

| Platform   | Post content via API? | Recommended approach |
|-----------|----------------------|------------------------|
| **Weibo** | ✅ Yes               | **weibo-api-1.0.0** — official OAuth2 + `statuses/update` (text) and `statuses/upload` (text + image). Straightforward, same pattern as x-api. |
| **WeChat**| ⚠️ Partial           | **wechat-official-1.0.0** — (1) **Publish article**: draft → submit → async callback (complex). (2) **Customer message**: send text/media to user within 48h after they messaged (simpler, different use case). |
| **Redbook**| ❌ No (read-only)   | **No “post note” API** for third parties. Open platform is e-commerce, local services, mini-program. Note-detail API is read-only. Document as “not available”; revisit if Xiaohongshu opens a creator API. |

---

## 1. Weibo (微博)

### Official platform

- **Open platform:** https://open.weibo.com/
- **API docs (wiki):** https://open.weibo.com/wiki/API文档_V2
- **Auth:** OAuth 2.0 — get `access_token` via authorization code flow. App Key + App Secret; redirect URI; user authorizes once, you store access_token (and refresh if supported).

### Posting weibo

| Action        | Endpoint | Method | Parameters |
|---------------|----------|--------|------------|
| **Text only** | `https://api.weibo.com/2/statuses/update.json` | POST | `access_token`, `status` (URL-encoded, ≤140 chars; or use `is_longtext=1` for long), `rip` (user IP, required) |
| **Text + image** | `https://api.weibo.com/2/statuses/upload` | POST multipart/form-data | `access_token`, `status`, `pic` (binary), `rip` |

- **rip:** Weibo requires the developer to pass the end-user’s real IP (e.g. `211.156.0.1`). When HomeClaw runs on behalf of a user, you can use the request’s client IP (from channel/request metadata) or a configured IP; document this in the skill.
- **Rate limits:** Apply; see [接口访问权限说明](https://open.weibo.com/wiki/Rate-limiting).

### Skill design: weibo-api-1.0.0

- **Same pattern as x-api-1.0.0:** `skills/weibo-api-1.0.0/` with SKILL.md, config.yml (`weibo_access_token` or env `WEIBO_ACCESS_TOKEN`), and `scripts/request.py`.
- **Actions:** `post <text>` → statuses/update (or statuses/upload if local image path passed); optional `get [count]` if we add “read my timeline” (e.g. `statuses/user_timeline`).
- **Token:** User obtains access_token from Weibo Open Platform (OAuth2 flow). Store in skill config or env; per-user key via `skill_api_keys` (see SkillApiKeysPerUserDesign.md) if multi-user.
- **rip:** In request.py, accept optional `--rip` or read from env (e.g. `WEIBO_CLIENT_IP`); otherwise use a default or leave empty (may get API error — document that user must set IP if required).

### Implementation steps

1. Add skill folder `weibo-api-1.0.0` with SKILL.md (description, trigger, auth, endpoints).
2. Add `config.yml` with optional `weibo_access_token`; document `WEIBO_ACCESS_TOKEN` env override and `WEIBO_CLIENT_IP` for rip.
3. Add `scripts/request.py`: `post <text>` (and optionally `post <text> <image_path>` for upload), URL-encode status, call statuses/update or statuses/upload with access_token and rip.
4. Register in KEYED_SKILLS (builtin) for per-user API key if desired.
5. Add to skills/README.md and docs_design/SocialMediaSupportAnalysis.md.

---

## 2. WeChat (微信)

### Official platform

- **Docs:** https://developers.weixin.qq.com/doc/offiaccount/Getting_Started/Overview.html  
- **Auth:** `access_token` via `GET https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid=APPID&secret=SECRET` (valid 7200s; must cache).

### Two use cases

#### A) Publish article to Official Account (公众号推文)

- **Flow:** Upload media (cover, images) → upload article to **draft** → **submit for publish** → result comes back **asynchronously** via callback to your server.
- **Endpoints:**  
  - Upload draft: `/cgi-bin/draft/add` (or similar).  
  - Submit: `/cgi-bin/freepublish/submit` — submits draft for review/publish; response only confirms submission.  
  - Status: callback event or query API (e.g. `/cgi-bin/freepublish/get`) for success/failure/rejection.
- **Implications:** Not a simple “post now” like Twitter/Weibo. Requires a **callback URL** and handling async events. Suitable for a **wechat-official-1.0.0** skill that supports “create draft + submit” and documents the callback requirement.

#### B) Send customer message (客服消息)

- **Rule:** Send to a user only within **48 hours** after they sent a message to your Official Account; **5 messages** per 48h window.
- **Endpoint:** `POST https://api.weixin.qq.com/cgi-bin/message/custom/send?access_token=ACCESS_TOKEN` with body (e.g. text, image).
- **Use case:** Reply to a specific user (e.g. “answer this follower”), not “post to my public timeline”. Different from “post to Weibo/X”.

### Skill design: wechat-official-1.0.0 (optional)

- **Option 1 — Publish only:** Skill that creates draft + submits for publish; document callback URL and async result. No customer message.
- **Option 2 — Customer message only:** Skill that sends a text/media message to a given `openid` (user who messaged in last 48h). Simpler; no callback needed for “send”.
- **Option 3 — Both:** One skill with two modes: `publish` (draft+submit + doc for callback) and `customer_send` (openid + content).

Recommendation: Start with **Option 2** (customer message) if you need “send a WeChat message to a user” from HomeClaw; add **Option 1** (publish) if you need to publish articles and can host the callback.

---

## 3. Redbook / Xiaohongshu (小红书)

### Official platform

- **Open platform:** https://open.xiaohongshu.com/  
- **Docs / school:** https://school.xiaohongshu.com/open/  
- **APIs:** Focus on **e-commerce** (products, orders, after-sales), **local services** (reservations, POI), **mini-program** development. There is a **note detail** API (read-only): get note title, content, images, engagement, author — for **query/analysis**, not for posting.

### Posting notes (发笔记)

- **No public “post note” or “create note” API** for third-party developers. The open platform does not expose a creator/content-publishing API like Weibo’s statuses/update.
- Workarounds (e.g. unofficial automation) are against ToS and fragile; not recommended.

### Skill design: Redbook

- **Do not implement a “post to Redbook” skill** with current official APIs — there is no supported way.
- **Optional:** A **redbook-read-1.0.0** skill that uses the note-detail (or similar) API to **fetch** note info by ID for analysis/search, if that fits your use case. This would be read-only.
- **Revisit** if Xiaohongshu later opens a **creator** or **content publishing** API.

---

## 4. Implementation priority

| Order | Skill | Scope | Effort |
|-------|-------|--------|--------|
| 1 | **weibo-api-1.0.0** | Post (and optionally read) weibo via official API | Low — same pattern as x-api; add rip handling. |
| 2 | **wechat-official-1.0.0** | Customer message (send to user in 48h) and/or publish (draft+submit + callback doc) | Medium — token cache, two flows, callback doc. |
| 3 | **Redbook** | No post skill; optional read-only “note detail” later | N/A for post; low if read-only later. |

---

## 5. References

- Weibo: [statuses/update](https://open.weibo.com/wiki/2/statuses/update), [statuses/upload](https://open.weibo.com/wiki/2/statuses/upload), [OAuth2](https://open.weibo.com/wiki/Oauth2/authorize).
- WeChat: [Publish](https://developers.weixin.qq.com/doc/offiaccount/Publish/Publish.html), [Customer message](https://developers.weixin.qq.com/doc/service/api/customer/message/api_sendcustommessage).
- Xiaohongshu: [Open platform](https://open.xiaohongshu.com/document), [Note detail (read)](https://cloud.tencent.com/developer/article/2571634) — read-only.
