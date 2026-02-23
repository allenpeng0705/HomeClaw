# System context: date/time and location

This doc designs how HomeClaw gets **current date/time** and (optionally) **location** so it can answer "how old am I?", "what day is it?", schedule relative to "now", and use location for weather or local context.

---

## 1. Problem

Today the agent:

- **Remembers** facts like "user's birthday is July 5, 1979" (from memory/profile).
- **Does not** automatically know the **current system date/time**. So when the user asks "how old am I?", it cannot compute age (current_date − birthday) unless it calls the **time** tool — and often it does not think to call it, so it may only say "you were born in 1979" instead of "you are 45 years old."
- **Scheduling** (TAM, cron, remind_me) already uses `datetime.now()` when executing (e.g. "in 5 minutes" → now + 5 min). So scheduling execution is correct. The gap is:
  - **General Q&A**: the model has no "today is YYYY-MM-DD" in context, so it can't compute age, "what day is it?", or "how many days until X?" without calling a tool.
  - **Formulating tool args**: when the model calls `remind_me(at_time="tomorrow 09:00")` or `record_date(event_date=...)`, it needs to know "today" to fill in dates correctly. If we inject current date into the system prompt, the model has it in context every turn.

**Location** is more complex: weather and "what time is it here?" need a default location. Possible sources include the **machine** (system APIs or IP-based geolocation), **chat history** (user said "I'm in Beijing"), **profile** (stored per user), or the **Companion app** (device sends location with the request). We need a clear priority order and fallbacks.

---

## 2. Current state

| Area | Current behavior |
|------|------------------|
| **System prompt** | No "current date/time" is injected. Workspace bootstrap, agent memory, daily memory, profile, skills, tools, etc. are injected; nothing says "Today is 2025-02-19, Wednesday; current time 14:30." |
| **`time` tool** | Exists in `tools/builtin.py`. Returns current date/time in ISO format (UTC). Description: "Get current date and time in ISO format (UTC)." The model *can* call it for "how old am I?" but often doesn't, and the description doesn't say "use for age calculation, today's date, scheduling." |
| **Scheduling** | TAM uses `datetime.now()` when building prompts and when scheduling one-shot/cron. So **execution** is already based on system time. No change needed there. |
| **Location** | No core-level default. Weather skill takes location from the message. Profile can store location/timezone per user. Request payload (e.g. from Companion) can carry extra fields but there is no standard `location` / `request_metadata.location` flow today. |

---

## 3. Design: datetime and location

### 3.1 Current datetime: use the **system** timezone

**Principle:** The current date and time injected into the prompt must be computed using the **same timezone as the system** (the machine running Core). That way "current time" matches what the user and the system see (e.g. if the server is in New York, we show New York time; if in UTC, we show UTC).

- **Implementation:** At request time, when building the system prompt:
  - Use **system local time**: e.g. `datetime.now()` (local) or `datetime.now().astimezone()` to get a timezone-aware "now" in the system's local timezone. Format as date (YYYY-MM-DD), time (HH:MM or HH:MM:SS), and day of week.
  - Optionally append the timezone name/label (e.g. "EST" or "UTC") so the model knows which zone this is.
- **No config override for display:** We do *not* use a configurable `default_timezone` to *display* current time. Display = system timezone only. (A config/default timezone can still be used later for *scheduling* if the server runs in UTC but the user is elsewhere — that's a separate concern; here we only define what "current datetime" means in the prompt: system time.)
- **Stability:** Build this block in try/except; on failure (e.g. system tz broken), fall back to UTC and minimal text. Never crash Core.

Example block (system in New York):

```text
## System context (use for age, "what day", scheduling, and relative time)
Current date: 2025-02-19. Day of week: Wednesday. Current time: 14:30 (system local).
Use this when answering questions about age, "what day is it?", "how many days until X?", or when scheduling (remind_me, record_date, cron_schedule). Scheduling execution uses system time; you supply dates/times relative to the current date above.
```

### 3.2 Location: multiple sources, priority order

Location is **optional** and can come from several places. We resolve it with a clear **priority order** so the model gets at most one "User location" (or "Current location") line in the system context.

Suggested order (highest priority first):

1. **Request / Companion**  
   The client (e.g. Companion app) can send location with the request. Options:
   - **POST /inbound** (or channel) body: e.g. `location`, `timezone`, or nested under `request_metadata`. Core, when building the prompt, reads e.g. `request.request_metadata.get("location")` or a top-level `location` from the inbound payload and, if present, uses it for this request.
   - This is the **best** for "where the user is right now" when the device has GPS and the app sends it.

2. **Profile**  
   User profile (see UserProfileDesign.md) can store `location` (and optionally `timezone`) per user. When building the system prompt we have `user_id` (and optionally `app_id`). If profile is enabled and the loaded profile contains `location`, use it when no request-level location is provided.

3. **System (machine)**  
   Try to infer the machine's location so the agent has a fallback (e.g. for "weather here" when the user and the server are in the same place). Options:
   - **IP-based geolocation**: Call a safe, best-effort service (or use a local GeoIP DB) to get city/country or lat/lon from the server's public IP. This is often wrong for cloud servers (data center location), so treat as low priority and optional.
   - **OS / system APIs**: On some platforms the system may expose timezone or location; if available and trusted, use that. Platform-dependent and may not exist on headless servers.
   - **Stability:** Any system-based lookup must be in try/except; on failure or missing data, simply omit the location line. Never crash Core.

4. **Chat history / memory**  
   The user may have said "I'm in Beijing" or "weather here" in past conversations. We could:
   - **RAG / agent memory**: When building context, if we already have memory search results, we could look for location-like facts and pass a short "User has mentioned location: …" line. This is more complex (requires heuristics or a dedicated memory slot) and can be a **later enhancement**.
   - For v1 we can **skip** this source and rely on request, profile, and (optionally) system.

**Config (core.yml)**  
- **No** `default_timezone` for *displaying* current datetime (we use system time).
- Optional **`default_location`**: If no location from request, profile, or system, and `default_location` is set in config, use it as a last fallback (e.g. for a single-user home server where the machine and user are in the same place).

**Which clients can send location**

- **Channels from other apps** (e.g. Line, WhatsApp, Telegram, email) generally **cannot** send location easily; we do not rely on them for request-level location.
- **Clients we can refine** should **ask for location permission** on their platform and, when granted, send location to Core:
  - **Companion app** — must request location permission on **all platforms** (iOS, Android, desktop); then use device GPS/location and send with each request (or periodically). Becomes the **latest location** for the **current user** (see §3.2.1).
  - **WebChat channel** — must ask for location permission when the browser supports geolocation; then send to Core.
  - **homeclaw-browser** control UI — must ask for location permission when the page/browser allows it; then send to Core.

So request-level location is primarily from Companion, WebChat, and homeclaw-browser. When Core receives `location` (e.g. in request body or `request_metadata`), it should **store it as the latest location for the resolved user** (system_user_id) so that when building the system prompt we use the right user's location. That way, if multiple family members use the Companion app and each is linked to a different user in user.yml, each gets their own latest location (see §3.2.1).

**Summary table**

| Source        | When to use | Notes |
|---------------|-------------|--------|
| Request (Companion, WebChat, browser) | Client sends `location` (or in `request_metadata`) | Best for "where the user is now"; store as **latest location per user** (system_user_id). Other channels typically don't send it. |
| Profile       | Per-user `location` (and optionally `timezone`) | Good for persistent user preference. |
| System        | IP geolocation or OS API (best-effort) | Fallback; often wrong on cloud. Optional. |
| Chat/memory   | From RAG / agent memory (e.g. "user said they're in X") | Future; can be added later. |
| Config        | `default_location` when nothing else available | Last fallback for single-user / same-machine setups. |

When we have a resolved location (from any source), add one line to the system context block, e.g. "User location: New York, US" or "Current location: Beijing (from device)." So the model can use it for weather or "what time is it here?" without the user repeating it every time.

**Where latest location is persisted:** Under the Core database directory: `{project_root}/database/latest_locations.json` (or the path from `config/core.yml` → `database.path` if set). File format: `{ "user_id": { "location": "...", "updated_at": "ISO8601" }, ... }`. When the Companion app does **not** combine to any user (picker = "System"), the app may still send location; Core stores it under the shared key `"companion"` so that **all users** can use it as a fallback when they have no per-user or profile location.

#### 3.2.1 Per-user latest location and Companion/app user picker

- **Latest location per user:** When Core receives `location` from a request, it should store it keyed by **system_user_id** (the user resolved from user.yml for this request). When building the system prompt, we look up "latest location for this system_user_id" and inject it. So each user (e.g. each family member) has their own latest location.
- **User picker (combined vs System):** Companion app, WebChat, and homeclaw-browser provide a **picker list**: users from user.yml plus **"System"**. When the user selects a **user** (combined), the client sends that **user_id** with every request; all chats go into that user's memory and chat histories with **channel = companion** (see CompanionFeatureDesign.md). When the user selects **"System"**, no combination — current behavior. So "combined" = per-user memory, profile, latest location; "System" = no per-user binding.
- **Location permission:** Companion app must request location permission on all platforms; WebChat and homeclaw-browser control UI must request location permission where the runtime supports it. Then these clients can send location to Core for latest-location-per-user when combined.

### 3.3 Inject the "System context" block

- **When:** At request time, when building `system_parts` in Core (same place we build workspace bootstrap, memory, etc.).
- **Content:**
  - **Always:** Current date, day of week, current time in **system local** timezone (see 3.1).
  - **Optional:** One line for location when available from request → profile → system → config (see 3.2).
- **Placement:** Near the start of the system prompt (e.g. right after workspace bootstrap or at the very beginning).
- **Stability:** Entire block in try/except; on any failure, omit or shorten the block (e.g. only "Current date: YYYY-MM-DD") and never crash Core.

### 3.4 Keep and improve the `time` tool

- **Keep** the `time` tool so the model can get a **fresh** timestamp when needed (e.g. after a long conversation, or when it wants explicit ISO/UTC).
- **Improve the description** so the model knows when to use it, e.g.:
  - "Get current date and time (system local or UTC). Use when you need precise current time (e.g. for age calculation, 'what day is it?', or scheduling). Optional: timezone name for another timezone."
- Optionally extend the tool to accept an optional `timezone` argument and return time in that timezone (e.g. "what time is it in Tokyo?"). The injected block still provides "now" in system time once per request; the tool remains for explicit or timezone-specific queries.

### 3.5 Scheduling (TAM, cron, remind_me)

- **No change to execution**: TAM and tools already use `datetime.now()` (and, where implemented, timezone from params) when scheduling. So scheduled jobs run at the correct system time.
- **Improvement**: With current date in the system prompt (in system timezone), the model can:
  - Compute "tomorrow", "next Monday", "in two weeks" correctly when calling `remind_me(at_time=...)` or `record_date(event_date=...)`.
  - Answer "how many days until my birthday?" using injected date + memory.

---

## 4. Location-specific behavior

| Use case | Today | With this design |
|----------|--------|-------------------|
| Weather | User says "weather in Beijing" or skill needs location from message. | Same; skill still gets location from args. If user says "how's the weather?" with no place, model can use injected "User location" (from request/Companion, profile, system, or config) when calling the skill. |
| "What time is it?" | Model can call `time` tool (returns UTC). | Injected "Current time" is in **system local** timezone; model can answer without calling the tool. For "what time is it in Tokyo?" model can call `time` with optional timezone (if we add that). |
| Scheduling | TAM uses system time; cron/remind_me use `datetime.now()`. | Unchanged. Model has "today" (system date) in context so it can pass correct dates/times in tool args. |

---

## 5. Implementation summary

1. **Core (core.py)**  
   When building `system_parts` for the main chat:
   - **Datetime:** Compute current date, time, day-of-week using **system local time** (e.g. `datetime.now()` or `datetime.now().astimezone()`). Format and add to a "## System context" block. No config timezone for this; we use the same timezone as the system.
   - **Location:** Resolve in order: (1) request (e.g. `request.request_metadata.get("location")` or inbound body `location`), (2) profile (`location` for this user), (3) system (IP geolocation or OS API, best-effort), (4) config `default_location`. Add one optional "User location: …" line when available.
   - Append the block near the start of `system_parts` (e.g. after workspace bootstrap). Wrap entire block in try/except; on error use minimal fallback (e.g. date only in UTC) and never crash Core.

2. **Config (core.yml, base/base.py)**  
   - **Do not** add `default_timezone` for displaying current datetime (we use system time).
   - Add optional **`default_location: ""`** (string) as last-resort fallback when no location from request, profile, or system.

3. **Request / Companion**  
   Document that clients (e.g. Companion app) can send location with the request so Core can inject it into the system context. For POST /inbound: accept e.g. `location` in the JSON body or under a metadata object, and merge into the request object that the orchestrator receives so `request.request_metadata.get("location")` (or equivalent) is available when building the prompt.

4. **Profile**  
   When profile is loaded for the user, if it contains `location` (and optionally `timezone` for other uses), use it for the "User location" line when no request-level location is provided.

5. **System location (optional)**  
   If implementing machine-based location: use IP geolocation or OS API in try/except; on failure or missing data, skip. Do not block or crash.

6. **`time` tool (tools/builtin.py)**  
   - Update the tool description to say to use it for age, "what day is it?", and scheduling when precise/fresh time is needed. Return system local time (or UTC) so it matches the injected block.
   - Optionally add a `timezone` parameter and return time in that timezone (e.g. via `zoneinfo`) for "what time is it in Tokyo?".

7. **Docs**  
   Update core-config or a short "System context" section to document: current datetime = system timezone; location = request → profile → system → config; Companion can send `location` with the request.

---

## 6. Guarantees

- **Stability**: Building the system context block must not crash Core (try/except; fallback to minimal text or omit block).
- **Datetime**: Current date/time in the prompt is always computed with the **same timezone as the system** (no config override for display).
- **Scheduling**: Execution already uses system time; this design only improves the model's context so it can formulate correct dates/times.
- **Backward compatibility**: Only optional `default_location` in config; if omitted, the block still shows current date/time (system local) and no location line when no other source provides it.

---

## 7. References

- **TimeAndSchedulingDesign.md** — TAM vs cron; scheduling execution uses system time.
- **UserProfileDesign.md** — Per-user profile; location (and optionally timezone) can be stored there.
- **tools/builtin.py** — `time` tool and scheduling tools (`remind_me`, `cron_schedule`, `record_date`).
- **base/base.py** — `PromptRequest.request_metadata`, `InboundRequest`; request payload can carry `location` for Companion.
