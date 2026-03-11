# Main LLM flow and companion “send more before response back”

Short summary of **how the main LLM works** and **whether the companion can send more messages before the previous response is sent back**.

---

## 1. How the main LLM works (summary)

### Entry

- **Companion / channels** send a user message via **POST /inbound** (or WebSocket /ws, or async POST with `async_mode: true`).
- Core turns that into a **PromptRequest** and calls **`core.process_text_message(request)`**.

### Inside `process_text_message`

1. **Identity and storage** — Resolve `user_id`, `app_id`, `session_id`, `friend_id` (and optional `system_user_id`). These decide which chat history and memory scope are used.

2. **Build user content** — Build the “user” content for this turn: text, optional images/audio/video (if the main LLM supports them), and optional files. File uploads can be processed (e.g. document understanding, add to KB) before the LLM sees them.

3. **Chat history** — Load recent turns from **chatDB** for this `(app_id, user_id, session_id, friend_id)` (e.g. last 6 rounds). These become the `messages` list for the LLM.

4. **Call `answer_from_memory`** — This is the main LLM + tools entry point (in `core/llm_loop.py`). It:
   - Builds **system prompt** (identity, time, agent/daily memory, RAG memory, knowledge base, skills list, plugins list, routing rules, friend preset, etc.).
   - Builds **tool list** (from registry; optionally filtered by friend preset; optionally without `route_to_tam` / `route_to_plugin` when not unified).
   - **LLM + tool loop** (up to 10 rounds):
     - **Acquire LLM semaphore** — `Util().openai_chat_completion_message(...)` uses **`_get_llm_semaphore(mtype)`** (local vs cloud). With default `llm_max_concurrent_local=1`, only one **local** LLM call runs at a time; others wait.
     - **Call LLM** — Async HTTP to the model server (or LiteLLM for cloud) with `messages` + `tools` and `tool_choice="auto"`. Timeout from **`llm_completion_timeout_seconds`** (or no timeout if set to 0).
     - **Handle response** — If the model returns **tool_calls**, run each tool (e.g. `run_skill`, `document_read`, `remind_me`), append tool results to `messages`, and loop again. If the model returns **no tool_calls** (only text), optional fallbacks (e.g. force-include auto_invoke, remind_me/cron fallback) may run; then the loop exits with that text (or a final LLM round if needed).
     - **Final response** — Last assistant message (or tool-result-based response) is returned.
   - **Save turn** — The (user_message, assistant_response) pair is appended to **chatDB** for this session.
   - **Return** — The response text (and optional image paths) go back to the caller.

5. **Response to client** — For **sync** POST /inbound, the HTTP response is sent only after `process_text_message` returns. For **stream: true**, the client gets SSE (e.g. progress events, then final “done”). For **async_mode**, Core returns 202 and the client polls GET /inbound/result.

### Important points

- **Async** — The LLM call is **async** (`await` on the HTTP call to the model server). The event loop can run other tasks while one request is waiting on the model.
- **One response per request** — Each POST /inbound is one user message and produces one response body (or one streamed “done”).
- **Serialization at LLM** — Concurrency is limited by **LLM semaphores** (e.g. one local LLM call at a time). So if two requests both use the local model, the second does not call the LLM until the first has **fully** finished (all tool rounds and final reply).

---

## 2. Can the companion send more messages before the previous response is back?

**Yes.** The companion can send another message (another POST /inbound) before the previous response has been returned. Core does **not** reject or queue-by-session; it accepts the new request and starts processing it.

### What happens in practice

- **Sync POST /inbound (typical)**  
  - Request 1: connection is open until `process_text_message` finishes (possibly 30s–300s+).  
  - If the companion opens a **second** connection and sends **Request 2** while Request 1 is still in progress:
    - Core accepts Request 2 and runs `process_text_message` for it.
    - Request 2 will **wait** when it tries to call the LLM, if it uses the same backend as Request 1 and the semaphore is full (e.g. `llm_max_concurrent_local=1`). So Request 2’s LLM call starts only after Request 1 has **fully** completed (including all tool rounds).
    - Request 1 and Request 2 may both read/write **chatDB** for the same session around the same time. So Request 2 might run with history that **does not yet include** Request 1’s Q&A (if Request 1 hasn’t written it when Request 2 reads). Ordering of turns is not guaranteed unless the client or server enforces it (e.g. client waits for response before sending next, or server adds a per-session queue).

- **Async mode** (`async_mode: true`)  
  - Companion gets **202** immediately and polls **GET /inbound/result?request_id=...**.  
  - It can send another async request and get another 202; multiple requests can be “in flight.” Same semaphore and chat DB behavior as above.

- **Stream** (`stream: true`)  
  - One connection, one request, SSE stream until “done.” To send a **second** message while the first is still streaming, the companion would use another connection (another POST with stream, or a non-stream POST). Then the same “two concurrent process_text_message” and semaphore/chat DB behavior applies.

### Summary for product/UX

| Question | Answer |
|----------|--------|
| Can the companion send another message before the previous response is back? | **Yes.** Core accepts the new request. |
| Will the second request run in parallel? | It runs, but its **LLM call** waits behind the first if they share the same LLM and concurrency is 1. So the second reply typically starts only after the first is fully done. |
| Can history get out of order? | **Yes.** There is no per-session lock. Request 2 might read chat history before Request 1 has written its turn, so the model might not see Request 1’s Q&A when answering Request 2. |
| Recommended for UX? | For predictable ordering and context, the companion usually should **wait for the previous response** (or at least for “done”) before sending the next user message, or use a single sequential pipeline. If you want to allow “send while previous is in progress,” consider a per-session queue or explicit “cancel previous” semantics and document that ordering may not be strict. |

---

## 3. Flow diagram (high level)

```
Companion POST /inbound (user message)
    → Core: handle_inbound_request
        → process_text_message
            → Load chat history (chatDB)
            → answer_from_memory
                → Build system prompt (memory, skills, plugins, …)
                → Build tool list (optional preset filter)
                → Loop (max 10 rounds):
                    → Acquire LLM semaphore (local or cloud)
                    → openai_chat_completion_message(messages, tools)
                    → If tool_calls: run tools, append results, repeat
                    → Else: exit with final text
                → Append (user, assistant) to chatDB
            → Return response text
    → Core returns HTTP 200 (or SSE “done” / 202 for async)
```

If the companion sends a **second** POST while the first is in the loop above, the second request enters the same pipeline; its LLM call is serialized by the semaphore when it uses the same model as the first.
