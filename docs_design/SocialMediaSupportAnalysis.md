# Social media support in HomeClaw — analysis

This doc analyzes how to support major social platforms (X/Twitter, Facebook, LinkedIn, Instagram, WeChat) in HomeClaw, based on the Gemini discussion and current APIs/gateways.

**Summary:** LinkedIn is already supported via **Maton**. X (Twitter), Facebook, and Instagram can be supported with **direct API skills** (official APIs) or via **aggregator APIs** (Hootsuite, Buffer) where available. WeChat is a special case (closed ecosystem, China-focused APIs).

---

## 0. Hootsuite vs official APIs (cost)

**Short answer: Prefer official APIs (X API + Meta Graph API) for X, Facebook, and Instagram — they are free or low-cost. Hootsuite is expensive; use it only as an optional skill for users who already pay for it.**

| Approach | Pros | Cons |
|----------|------|------|
| **Official APIs (X + Meta)** | **Free** (or low-cost tiers). No Hootsuite subscription. Two skills: **x-api-1.0.0**, **meta-social-1.0.0** (FB + IG). | One skill per "family" (X, Meta); user connects each app. |
| **One Hootsuite skill** | One OAuth, one skill for X, Facebook, LinkedIn, Instagram. | **Requires paid Hootsuite** — expensive; many users won't have it. |
| **Maton** | One key; already gives **LinkedIn** (and 100+ other services). | Maton doesn't offer X, Facebook, or Instagram. |

**Recommendation:**

- **Default: x-api-1.0.0** (X API v2) and **meta-social-1.0.0** (Facebook Page + Instagram via Meta Graph API) — free, no Hootsuite.
- **Keep Maton** for LinkedIn (and everything else).
- **Optional later:** Add **hootsuite-1.0.0** only if you want to support users who already have a Hootsuite subscription.
- Keep **social-media-agent** for X via browser as a fallback (no API key).

So: **official APIs first**; Hootsuite as an optional add-on for paying subscribers.

---

## 1. What we already have

| Platform | In HomeClaw | How |
|----------|-------------|-----|
| **LinkedIn** | ✅ | **Maton** (`linkedin` app) — posts, profile, shares, media. Also **linkedin-writer-1.0.0** (content style) and **social-media-agent-1.0.0** (strategy + X via browser). |
| **X (Twitter)** | Partial | **social-media-agent-1.0.0** — uses **browser automation** (open x.com, compose, post). No X API key needed; no official posting API in a skill. |
| **WhatsApp Business** | ✅ | **Maton** (`whatsapp-business`) — graph.facebook.com. |
| **Snapchat** | Via Maton | **Maton** (`snapchat`) — ads API only (campaigns, creatives), not general posting. |

Maton does **not** currently list X (Twitter), Facebook Pages, or Instagram in its [Supported Services](https://github.com/maton-ai/api-gateway-skill) table. So for those we need either direct APIs or another gateway/aggregator.

---

## 2. Platform-by-platform analysis

### X (Twitter)

| Approach | Feasibility | Notes |
|----------|-------------|------|
| **Maton** | ❌ | Not in Maton’s supported list. |
| **X API v2** | ✅ | Official [POST /2/tweets](https://developer.x.com/en/docs/twitter-api/tweets/manage-tweets/api-reference/post-tweets). OAuth 1.0a or OAuth 2.0 PKCE. Need developer account + app. **Skill idea:** `x-post-1.0.0` or `twitter-api-1.0.0` — user connects app, skill calls X API (post, read timeline, etc.) via config/script. |
| **Hootsuite API** | ✅ | [Hootsuite Publishing API](https://developer.hootsuite.com/docs/api-overview) — schedule/post to Twitter (and Facebook, LinkedIn, Instagram). OAuth 2.0. **Skill idea:** `hootsuite-1.0.0` — one skill for multi-platform posting if user uses Hootsuite. |
| **Buffer API** | ⚠️ | [Buffer API](https://buffer.com/developers/api) exists but is being rebuilt; not accepting new dev apps. Wait for new API or use only if already integrated. |
| **Browser (current)** | ✅ | **social-media-agent-1.0.0** — no API key; uses browser to post. Good fallback. |

**Recommendation:** Add an **X (Twitter) API skill** (OAuth + POST /2/tweets, optional read) for users who have a developer app. Keep social-media-agent for users who don’t.

---

### Facebook (Pages / Meta)

| Approach | Feasibility | Notes |
|----------|-------------|------|
| **Maton** | ❌ | No Facebook Pages in Maton list (only WhatsApp Business via Meta graph). |
| **Meta Graph API** | ✅ | [Pages API](https://developers.facebook.com/docs/pages-api) — POST to `/{page-id}/feed`, scheduled posts, page token with `pages_manage_posts`. **Skill idea:** `facebook-pages-1.0.0` — post to Page, list scheduled posts; user connects app and gets Page token. |
| **Hootsuite API** | ✅ | Supports Facebook in Publishing API. Same “one skill for Hootsuite” idea. |
| **Buffer** | ⚠️ | Same as X — API in transition. |

**Recommendation:** Add a **Facebook Pages skill** using Meta Graph API (post, schedule) for users with a Meta app and Page. Optionally later add Hootsuite skill for multi-platform.

---

### Instagram

| Approach | Feasibility | Notes |
|----------|-------------|------|
| **Maton** | ❌ | Not in Maton list. |
| **Meta Graph API (Instagram)** | ✅ | [Instagram Graph API](https://developers.facebook.com/docs/instagram-api) — Business/Creator accounts; publish content, insights. Requires Facebook Page linked to IG account. **Skill idea:** `instagram-graph-1.0.0` — post media/captions, read insights; same app as Facebook. |
| **Hootsuite API** | ✅ | Supports Instagram in Publishing API. |

**Recommendation:** Add **Instagram skill** via Meta Graph API (same Meta app as Facebook Pages) for business/creator accounts. Or cover both in one **meta-social-1.0.0** skill (Facebook Pages + Instagram).

---

### LinkedIn

| Approach | Feasibility | Notes |
|----------|-------------|------|
| **Maton** | ✅ | Already have **maton-api-gateway** with `linkedin` app — posts, profile, shares, media. Use `request.py` with app=`linkedin`. |
| **linkedin-writer-1.0.0** | ✅ | Content style only; no API. Keep for “write a LinkedIn post” tone. |
| **RedactAI / TweetHunter-style** | Niche | Third-party AI for content; not needed for “post to LinkedIn” — Maton + references cover that. |

**Recommendation:** No new skill needed. Document in USAGE.md / social docs: “Post to LinkedIn via Maton (connect LinkedIn at maton.ai).”

---

### WeChat

| Approach | Feasibility | Notes |
|----------|-------------|------|
| **Official WeChat API** | ⚠️ | [Official Accounts / WeChat Pay](https://developers.weixin.qq.com/doc/offiaccount/en/Getting_Started/Overview.html) — strong focus on China, app approval, server in region. Not a simple “one OAuth and post” like X or Meta. |
| **Global tools (Hootsuite, Buffer)** | ❌ | Typically do not support WeChat (closed ecosystem). |
| **JINGdigital / Parllay** | External | China-market platforms; would require their API and possibly separate skill/integration. |

**Recommendation:** Treat WeChat as **out of scope** for a first wave of “major social” skills unless you have a concrete WeChat Official Account or partner API. If needed later, add a dedicated **WeChat skill** (or JINGdigital/Parllay integration) with clear setup steps.

---

## 3. Third-party aggregators (one skill, multiple platforms)

| Service | Platforms | API status | Skill idea |
|---------|-----------|------------|------------|
| **Hootsuite** | X, Facebook, LinkedIn, Instagram, Pinterest | ✅ REST API, OAuth 2.0, [Publishing API](https://developer.hootsuite.com/docs/api-overview) | **hootsuite-1.0.0** — post/schedule to connected networks; one token, multi-platform. |
| **Buffer** | X, Facebook, LinkedIn | ⚠️ Rebuilding API; not accepting new apps | Wait for new Buffer API, then consider **buffer-1.0.0**. |
| **SocialBee** | X, LinkedIn, Facebook | Check if public API | If they expose an API, same pattern as Hootsuite skill. |
| **Sprout Social** | Many (sentiment, listening) | Enterprise API | More analytics/listening than “post from HomeClaw”; lower priority unless you need brand monitoring. |
| **Make (Integromat)** | LinkedIn, X, etc. via scenarios | Make has API; user builds scenarios | Not a “post to X/LinkedIn” skill per se; user would build a Make scenario and we could trigger it (webhook) from a skill. Possible but more custom. |

**Recommendation:** Prefer **x-api-1.0.0** and **meta-social-1.0.0** (official APIs, free). Add **Hootsuite** skill only for users who already have a subscription. Skip Buffer until the new API is available.

---

## 4. Suggested skill roadmap

| Priority | Skill | What it does | Auth / dependency |
|----------|-------|--------------|-------------------|
| 1 | Already have | **Maton** — LinkedIn, WhatsApp; **social-media-agent** — X via browser | Maton key; no key for browser X |
| 2 | **x-api-1.0.0** | Post tweet (and optional read) via X API v2 | **Free tier** — user’s X developer app, OAuth |
| 3 | **meta-social-1.0.0** | Post to **Facebook Page** and **Instagram** (Graph API) | **Free** — user’s Meta app, Page + IG linked |
| 4 | (Optional) **hootsuite-1.0.0** | Only for users who already have Hootsuite — X, FB, LinkedIn, IG from one dashboard | **Paid** — Hootsuite subscription |
| Later | **buffer-1.0.0** | Same idea when Buffer’s new API is available | Buffer OAuth |
| Later | **WeChat** | Only if you need Official Account automation and have API access | WeChat app credentials / partner |

---

## 5. Implementation pattern for new skills

- **Direct API skills (X, Meta):** Same pattern as **outlook-api** or **maton request.py** — skill folder with SKILL.md (base URL, auth, endpoints), optional `config.yml` for API key or token, optional `scripts/request.py` (or similar) that calls the official API. User gets token from X/Meta developer portal; skill uses it.
- **Aggregator skill (Hootsuite):** One OAuth with Hootsuite; skill calls Hootsuite Publishing API with profile IDs for X, Facebook, etc. References similar to maton (one doc per supported network if needed).
- **User guide:** Add a **USAGE.md** (and optionally `skills_include_body_for`) so the model can answer “how do I post to X/Facebook/LinkedIn?” — with LinkedIn pointing to Maton and USAGE.md listing example phrases for each platform.

---

## 6. Summary table

| Platform | Today in HomeClaw | Recommended next step |
|----------|-------------------|------------------------|
| **LinkedIn** | Maton + linkedin-writer | Keep as-is (Maton). |
| **X (Twitter)** | Browser (social-media-agent) | Add **x-api-1.0.0** (X API v2, free tier); keep browser as fallback. |
| **Facebook** | — | Add **meta-social-1.0.0** (Graph API, free). |
| **Instagram** | — | Same **meta-social-1.0.0** (Graph API, free). |
| **WeChat** | — | Out of scope for first wave. |
| **Hootsuite** | — | Optional later for users who already pay; not default. |

**Bottom line:** Use **official APIs** (X API + Meta Graph API) for X, Facebook, and Instagram — free/low-cost, no Hootsuite. **Maton** for LinkedIn. Add Hootsuite skill only if you want to support users who already have a Hootsuite subscription.

---

## 7. Chinese platforms: Weibo, WeChat, Redbook

See **docs_design/WeiboWeChatRedbookSkillsInvestigation.md** for a full investigation.

| Platform | Post via API? | Recommendation |
|----------|----------------|-----------------|
| **Weibo** | ✅ Yes | **weibo-api-1.0.0** — official OAuth2 + `statuses/update` (text) and `statuses/upload` (text + image). Same pattern as x-api; note `rip` (user IP) required by API. |
| **WeChat** | ⚠️ Partial | **wechat-official-1.0.0** — (1) Publish article: draft → submit → async callback. (2) Customer message: send to user within 48h after they messaged (simpler). |
| **Redbook (小红书)** | ❌ No | No public “post note” API. Open platform is e-commerce / mini-program; note APIs are read-only. No post skill; optional read-only later. |
