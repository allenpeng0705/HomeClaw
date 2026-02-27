# Step 2: Request context user_id + friend_id — done

**Design ref:** [UserFriendsModelFullDesign.md](../UserFriendsModelFullDesign.md) Implementation step 2.

**Goal:** Every request that goes through Core has **user_id** (system user id) and **friend_id** (which friend this conversation is with). For channels, set friend_id = "HomeClaw". For Companion/inbound, client sends friend_id or we default to "HomeClaw". Thread (user_id, friend_id) through ToolContext so tools and later steps can use them. **No storage key or session changes yet** (those are Step 8); only request and context carry friend_id.

---

## 1. What was implemented

### 1.1 PromptRequest (base/base.py)

- Added **friend_id: Optional[str] = None**. Meaning: which friend this conversation is with (e.g. "HomeClaw", "Sabrina"). Channels use "HomeClaw"; Companion sends from client. When not set, callers treat as "HomeClaw".

### 1.2 InboundRequest (base/base.py)

- Added **friend_id: Optional[str] = None**. Client can send `friend_id` in POST /inbound body or in WebSocket message. Omitted or empty → normalized to "HomeClaw" in Core.

### 1.3 ToolContext (base/tools.py)

- Added **friend_id: Optional[str] = None**. When Core builds ToolContext from a request, it sets `friend_id=(str(getattr(request, "friend_id", None) or "").strip() or "HomeClaw"` (safe for non-string). Tools (and later steps) can use `context.friend_id`; when missing, use "HomeClaw" for safety.

### 1.4 Channel requests (core/core.py)

- **/process** (request queue from channels): after `request.system_user_id = user.id or user.name`, set **request.friend_id = "HomeClaw"**.
- **/local_chat**: same — **request.friend_id = "HomeClaw"** after setting system_user_id.
- **Request queue consumer** (loop that processes requests from the queue): same — **request.friend_id = "HomeClaw"** for each channel request.

So all channel traffic has friend_id = "HomeClaw".

### 1.5 Inbound and WebSocket (core/core.py, core/routes/websocket_routes.py)

- **_handle_inbound_request_impl**:  
  - **inbound_friend_id** = `(str(_fid).strip() if _fid is not None else "") or "HomeClaw"` where `_fid = getattr(request, "friend_id", None)` (safe for non-string).  
  - Pass **friend_id=inbound_friend_id** into **PromptRequest**(...).  
  - After permission check, set **pr.friend_id = inbound_friend_id** (redundant with constructor but explicit).
- **POST /inbound**: Body may include **friend_id**; InboundRequest parses it (Pydantic). No extra code needed.
- **WebSocket /ws**: When building **InboundRequest** from JSON, pass **friend_id=(data.get("friend_id") or "").strip() or None**. Core then normalizes to "HomeClaw" when None/empty.

### 1.6 ToolContext built from request (core/core.py)

- **context_flush** (memory flush): **friend_id=(str(getattr(request, "friend_id", None) or "").strip() or "HomeClaw"** (safe for non-string).
- **context** (main tool loop): same.

So every ToolContext built from a PromptRequest in process_text_message carries friend_id.

### 1.7 Cron / TAM (tools/builtin.py, core/tam.py)

- No change. ToolContext built there has no request or a synthetic request; **friend_id** is left default **None**. In later steps, cron can pass friend_id via params when we add (user_id, friend_id) to cron. Tools that need friend_id should use `getattr(context, "friend_id", None) or "HomeClaw"` so cron paths stay safe.

---

## 2. Files touched

| File | Change |
|------|--------|
| **base/base.py** | PromptRequest: + friend_id. InboundRequest: + friend_id. |
| **base/tools.py** | ToolContext: + friend_id. |
| **core/core.py** | /process, /local_chat, request-queue loop: set request.friend_id = "HomeClaw". Inbound: inbound_friend_id, pass into PromptRequest and set pr.friend_id. Both ToolContext builds: + friend_id from request. |
| **core/routes/websocket_routes.py** | InboundRequest(..., friend_id=...). |

---

## 3. Robustness and safety

- **getattr(request, "friend_id", None)**: Safe when request is old or missing the field.  
- **(.strip() or "HomeClaw")**: Ensures we never pass None into storage later; default is always "HomeClaw".  
- **Channels**: Always set friend_id explicitly so no path leaves it unset.  
- **Inbound/WS**: Normalize once; no crash on missing or bad type (Pydantic/getattr handle it).  
- **ToolContext**: Optional field; existing callers that don’t set friend_id get None; tools can default with `getattr(context, "friend_id", None) or "HomeClaw"`.
- **Non-string friend_id**: If a bad client sends `friend_id` as int/other type, calling `.strip()` would raise. Core now normalizes before strip: inbound uses `(str(_fid).strip() if _fid is not None else "") or "HomeClaw"`; both ToolContext builds use `(str(getattr(request, "friend_id", None) or "").strip() or "HomeClaw"`. So Core never crashes on malformed friend_id.

---

## 4. What Step 2 does *not* do

- **No chat/session key changes**: Session and chat history keys are unchanged (Step 8).  
- **No memory path changes**: Memory paths still per user (or global); Step 3 will switch to (user_id, friend_id).  
- **No RAG/KB/cron key changes**: Steps 9–10.  
- **No Companion UI**: Client can send friend_id; no change to Companion app yet (Step 12).

---

## 5. Logic summary for review

1. **Channels**: Every channel request gets **friend_id = "HomeClaw"** in the three places we set system_user_id.  
2. **Inbound/WS**: **friend_id** comes from body or message; normalized to non-empty string, default **"HomeClaw"**; stored on PromptRequest and used when building ToolContext.  
3. **ToolContext**: Carries **friend_id** whenever built from a real request; otherwise None (cron/TAM). Callers that need a value use **getattr(context, "friend_id", None) or "HomeClaw"**.  
4. **Storage**: Not yet keyed by friend_id; that is Step 8 (chat/sessions) and related steps. Step 2 only adds the field to request and context.

---

---

## 6. Review (logic + robustness)

- **Logic**: Channels always set friend_id = "HomeClaw"; inbound/WS take client friend_id and default to "HomeClaw"; ToolContext carries that value from the request. No storage keys changed. ✓  
- **Robustness**: getattr(..., None) used everywhere; default "HomeClaw" applied after normalization; non-string friend_id is converted with str() before .strip() in all three places (inbound_friend_id, context_flush, main context) so Core never crashes on bad client data. ✓  

**Step 2 is complete.** Next: Step 3 (Memory (MD) paths per (user_id, friend_id)).
