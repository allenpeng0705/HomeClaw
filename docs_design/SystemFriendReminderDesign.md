# Design discussion: system friend “Reminder” per user (cron/reminder focus)

**Status:** Discussion / design only — no implementation yet.

**Target:** When the user uses the **Reminder** friend, reminder/cron should **succeed much more easily**, even with a **small local model**. We achieve this by **not injecting too much** into the context — only reminder/cron tools and related bits — so the model has a small, focused set to choose from.

**Creation and result:** How to create cron/reminder and how to show the result is **the same for all users and all friends**. The Reminder system friend only changes **context** (predefined tools/skills/plugins + optimized histories). Talk with Reminder about other things and it may not be so useful; it does a good job on scheduling.

---

## 1. The problem we’re solving

Cron and reminder behaviour can be **unstable** when the user asks for them in a normal friend’s chat: the LLM sees the **full tool set** (dozens of tools), so it may:

- Pick the wrong tool instead of `remind_me` or cron-related tools.
- Behave inconsistently (sometimes works, sometimes doesn’t).

So: **tool selection for cron/reminder is harder and less stable when the model has many tools to choose from.**

---

## 2. The idea: a Reminder friend with **only** cron + reminder tools

- Add a **system friend** “Reminder” (or similar name) for **each user**.
- **Reminder friend:** when the user talks to this friend, Core **does not** inject the full set of skills, tools, and plugins. It injects **only** what is used for Reminder: cron and reminder tools (and any reminder-related skills/plugins). Nothing else.
- **All other friends:** unchanged — full skills, tools, and plugins as today; they can still use cron/reminder if the LLM chooses correctly, but tool selection is harder there.

So:

- **Reminder chat** = small, fixed tool set (cron + reminder only) → **we don't inject too much** → correct tool is much easier to select → **succeeds much more easily even with a small local model**.
- **Other chats** = full tool set; cron/reminder still possible but not guaranteed to be stable, especially for small models.

That way the Reminder friend is the **dedicated, reliable** entry point for “only do cron and reminder.” With minimal context (few tools, short prompt), even a **small local model** can succeed there.

---

## 3. What “system friend” could mean

### 3.1 Only inject what’s used for Reminder (no full skills/tools/plugins)

- When **friend_id = Reminder** (user is in the Reminder chat), Core **does not** inject the full skills, tools, and plugins. It injects **only** what is needed for cron and reminder:
  - **Tools:** only cron + reminder tools (e.g. `remind_me`, list reminders, and any cron-related tools). No other tools.
  - **Skills:** only any skills used for reminder/cron, or none if not needed. No other skills.
  - **Plugins:** only any plugins used for reminder/cron, or none. No other plugins.
- So the model sees a **minimal, focused** context (we **don't inject too much**) → correct tool is **easy to select** → reminder/cron **succeeds much more easily, even with a small local model**.
- Other friends’ chats get the **full** injection (all skills, tools, plugins) as today.

### 3.2 Delivery: keep current path and logic; Reminder as fallback only

- **We do not change** the current delivery path and logic. Reminders and cron results are delivered the same way as today (to the user/channel/friend they belong to).
- **Target depends on who created or owns the reminder:** If the user created a reminder while chatting with Friend A (or with “HomeClaw” or another system friend), the reminder can be delivered to that friend’s conversation. So **any friend** (including system friend “HomeClaw”) may have cron/reminder messages sent to them when that’s the right target.
- **Reminder friend is only a fallback:** When the system **cannot determine** where to send (e.g. no clear sender, no channel, legacy job), it is fine to send to “Reminder” as the default. So “Reminder” is the **exception/fallback** destination, not the single delivery target for all reminders and cron.

### 3.3 Inbound: when the user talks to Reminder

- When the user **selects** the Reminder friend and sends a message (e.g. “Remind me in 15 minutes”, “What are my upcoming reminders?”, “Cancel the 3pm reminder”):
  - The client sends `friend_id=Reminder` (or the system friend’s id).
  - Core treats this conversation as **reminder-only**:
    - **Inject only** reminder/cron tools, and only any reminder-related skills/plugins (do not inject all skills, tools, or plugins).
    - Short system prompt: e.g. “You are the Reminder assistant. You only schedule and list reminders. Use only the provided tools.”
    - TAM and cron logic are the “identity” of this friend (no general chitchat, or minimal).

So:
- **Delivery:** Keep current delivery path and logic. Send to the appropriate target (friend/HomeClaw/etc.). Use **Reminder only when we cannot find where to send** (fallback).
- **Inbound:** When the user talks to the Reminder friend, Core injects only reminder/cron tools (and related skills/plugins) so the LLM selects the correct tool easily.

### 3.4 Same creation and result logic for everyone; Reminder = context only

- **How to create cron/reminder** and **how to show the result** is **the same for all users and all friends**. No different code path for the Reminder friend. TAM, cron, and delivery use the same logic whether the user is chatting with Reminder, HomeClaw, or any other friend.
- The **Reminder system friend does one thing**: it only changes **context**. When you are in the Reminder chat we inject **predefined** (limited) skills, tools, and plugins, plus **optimized histories**. All of that is about context — we do not change how reminders are created or how results are delivered.
- So: if you talk with Reminder about **other things** (e.g. weather, general chat), it may not be so useful (limited tools). But it **does a good job on scheduling** because the context is focused. Same creation and result behaviour everywhere; only the context in the Reminder chat is optimized for scheduling.

---

## 4. Would it make cron/reminder “much better”?

| Aspect | Effect |
|--------|--------|
| **Minimal context / small local model** | We **don't inject too much**: only reminder/cron tools (and related skills/plugins). So the user can use **Reminder** and **succeed much more easily even with a small local model**. |
| **Intent focus** | When the user is in the Reminder chat, Core injects only reminder/cron tools; less ambiguity, correct tool easy to select. |
| **Delivery** | Current delivery path and logic unchanged. Reminders/cron send to the target they belong to (e.g. the friend or “HomeClaw” the user was with). **Reminder** is used only as a **fallback** when the system cannot determine where to send. |
| **UX clarity** | User has a dedicated place to “talk about reminders” (Reminder friend) with stable behaviour; delivery still goes to the right conversation per existing logic. |
| **Extensibility** | Same pattern could be reused for other system friends later (e.g. “Calendar”, “Alerts”) if needed. |

So: **yes, it can make the cron/reminder feature meaningfully better** — minimal context in the Reminder chat so it **succeeds much more easily even with a small local model**; delivery keeps current behaviour (Reminder only as fallback when target is unknown).

---

## 5. Design choices to decide

### 5.1 How does each user get this friend?

- **Option A – Injected at runtime**  
  Core (or the API that returns “my friends”) **adds** a virtual “Reminder” friend to every user’s list. No change to `user.yml` or Friends plugin data; it’s a fixed system friend that’s always present.
- **Option B – Configured per user**  
  Each user has “Reminder” (or a system friend id) in their `friends` list in config. More explicit but repetitive and easy to forget for new users.
- **Option C – Single system-friend definition**  
  One global definition (e.g. id `"Reminder"`, name “Reminder”) that Core treats as a system friend and automatically “adds” to every user when returning friends or when handling delivery.

**Recommendation:** Option A or C so every user automatically has the Reminder friend without per-user config.

### 5.2 Identity and id

- Use a **fixed friend_id** (e.g. `"Reminder"` or `"system_reminder"`) so that:
  - Client sends `friend_id=Reminder` when the user is in the Reminder chat.
  - Core recognizes “conversation with Reminder” and injects only reminder/cron tools (and related skills/plugins).
  - TAM / cron use current delivery logic; they use Reminder only as **fallback** when the system cannot determine the delivery target (not as the default for all).

### 5.3 What “Reminder-only” means in code

- **Delivery:** Keep current TAM/cron delivery path and logic. Deliver to the appropriate target (the friend or “HomeClaw” the reminder/cron belongs to). Only when the system **cannot find** where to send (e.g. unknown sender, legacy), deliver to “Reminder” as fallback.
- **Inbound:** When `friend_id=Reminder` (or equivalent), Core:
  - **Does not inject** all skills, tools, and plugins. **Only** injects what is used for Reminder (cron + reminder tools; any reminder-related skills/plugins if needed).
  - Injects a short system line: “This is the Reminder assistant; you only schedule and list reminders. Use only the provided tools.”
  - Keeps conversation history per (user_id, Reminder) so the thread is dedicated.

### 5.4 Backward compatibility

- Current delivery behaviour stays. No change to “where” reminders and cron are sent by default. Reminder is only used as fallback when the system cannot determine the target.

---

## 6. Summary

- **Idea:** One system friend “Reminder” per user. For this friend we **do not** inject all skills, tools, and plugins — **only** what is used for Reminder (cron + reminder). Creation and result use the same logic for all users/friends; Reminder only changes context (predefined tools/skills/plugins + optimized histories). Other topics in Reminder chat may not be so useful; it does a good job on scheduling.
- **Benefits:** Minimal injected surface for the Reminder chat → correct tool easy to select → more stable cron/reminder behaviour; clear place to *talk about* reminders; delivery keeps current path (Reminder only as fallback when target unknown); reusable pattern for other system friends.
- **Main decisions:** (1) How the friend appears in the list (injected vs configured), (2) fixed id (e.g. `"Reminder"`), (3) exact list of tools/skills/plugins to inject for Reminder only. **Delivery:** keep current path and logic; use Reminder only as fallback when the system cannot determine where to send.
- **Framework (§10):** If limited tools/skills/plugins and optimized history are **configurable per friend**, we get a reusable framework; Reminder and Finder are examples, and **users can customize** their own friends with restricted context too.

No code changes in this step — this doc is for discussion and design alignment. Once you’re happy with the direction, we can outline concrete steps (API shape, TAM/cron delivery, Companion changes) and then implement.

---

## 7. Pros and cons (detailed discussion)

### 7.1 Pros

| Benefit | Why it helps |
|--------|----------------|
| **Stable tool selection** | With only cron + reminder tools in the Reminder chat, the LLM has a small, fixed set. It is much less likely to pick the wrong tool (e.g. `run_skill` or something unrelated). Correct tool → more reliable behaviour. |
| **Predictable behaviour** | Same request in the Reminder chat tends to get the same handling. No “sometimes it works in Friend A’s chat, sometimes it doesn’t” — Reminder is the dedicated, constrained path. |
| **Lower prompt/token load** | Fewer tools (and no extra skills/plugins) mean a smaller system prompt and fewer tokens per request. Cheaper and often faster. |
| **Clear mental model for users** | “Use Reminder for reminders” is easy to explain. One place to create/list/cancel reminders and see cron output. Less confusion than “you can ask any friend but it might not work.” |
| **Fallback when target unknown** | When the system cannot determine where to deliver (e.g. no clear sender/channel), sending to “Reminder” is a sensible fallback. Normal delivery still uses current path (to the friend or “HomeClaw” that created or owns the reminder/cron). |
| **Easier to test and maintain** | Reminder path has a narrow contract (only these tools, this prompt). Easier to add tests and to change reminder logic without touching the full tool/skill set. |
| **Reusable pattern** | Same idea can be used later for other system friends (e.g. “Calendar”, “Alerts”) with their own restricted tool sets. |

### 7.2 Cons and risks

| Drawback / risk | Why it’s a concern | Mitigation |
|-----------------|--------------------|------------|
| **Two places to do reminders** | User can still say “remind me in 15 min” in another friend’s chat. There we keep full tools, so behaviour may be less stable. User might not know they “should” use Reminder. | Document that Reminder is the recommended place for reminders. Optionally add a short hint in other chats: “For reminders, try the Reminder friend.” |
| **Extra concept** | “System friend” and “friend_id = Reminder” are new. More code paths and config to understand. | Keep the rule simple: one fixed id (e.g. `Reminder`), one injection list. Document clearly. |
| **Maintaining the “Reminder only” list** | We must keep the list of tools/skills/plugins for Reminder in sync with actual reminder/cron features. If we add a new reminder tool and forget to add it to the Reminder list, the Reminder chat won’t use it. | Define the list in one place (e.g. config or constant). Use it both for “inject for Reminder” and for docs. Review when adding reminder/cron features. |
| **Rigid boundary** | In the Reminder chat the user cannot do anything else (e.g. “remind me in 15 min and add this to my notes”). That might feel limiting. | Accept the trade-off: Reminder = reminder-only for stability. For combined intents, user uses another friend’s chat. |
| **Client and Core changes** | Companion (and any client) must show Reminder in the friend list and send `friend_id=Reminder`. Core must branch on friend_id and inject a subset of tools/skills/plugins. | One-time implementation; then the behaviour is consistent. |

### 7.3 Edge cases and nuances

- **User asks something off-topic in Reminder chat** (e.g. “What’s the weather?”). With only reminder tools, the model has no weather tool. It should say something like “I can only help with reminders. For other things, use another chat.” That’s acceptable and keeps the Reminder path focused.
- **Reminder delivery:** We keep current delivery logic (send to the friend/HomeClaw the reminder belongs to). When target is unknown, we fall back to Reminder. Push/notification behaviour stays as today so the user gets notified regardless of which conversation the reminder is delivered to.
- **Backward compatibility:** Delivery logic stays as today. When we can’t determine the target, we use “Reminder” as fallback. Reminders created in a specific friend’s chat (or “HomeClaw”) are delivered to that conversation.

### 7.4 Alternatives (and why we still prefer the Reminder friend)

| Alternative | Pros | Cons |
|-------------|------|------|
| **Improve tool descriptions / prompts only** | No new concept; works in every chat. | With many tools, the LLM still often picks wrong. Descriptions alone don’t fix the “too many choices” problem. |
| **Force-include remind_me in every chat** | remind_me is always available. | Other tools still compete; model can still call the wrong one. Doesn’t give a dedicated “reminder-only” context. |
| **Separate “Reminder” app or screen (no friend)** | Clear separation. | Different UX (not “chat with a friend”); would need separate API and UI; doesn’t reuse the friend/conversation model. |
| **Reminder friend with full tools but stronger prompt** | User can do mixed intents in Reminder chat. | Same instability: many tools → wrong tool selection. Defeats the main goal. |

So: a **dedicated Reminder friend with restricted injection** is the option that directly addresses “LLM picks wrong tool when there are too many.”

### 7.5 Verdict

- **Pros outweigh cons** if the main goal is **more stable cron/reminder behaviour** and a **clear, single place** for reminder/cron. The cost is one extra concept (system friend), a maintained “Reminder only” list, and some client/Core branching.
- **Worth doing** when unreliable reminder behaviour in normal chats is a real pain. If reminder usage is rare and “good enough” today, the Reminder friend is still an improvement but less urgent.
- **Recommendation:** Treat the design as **good** and proceed to implementation details (exact tool list for Reminder, where to branch in Core, how to inject the friend in the API) once you're satisfied with this pros/cons discussion.

---

## 8. Evaluation: does this design give us many benefits?

**Yes.** The Reminder friend design gives clear benefits:

1. **Easier success with small local models** — By not injecting too much (only reminder/cron tools, short prompt, optionally less memory), the model has a small, focused context. Tool selection is simpler; reminder/cron is much more likely to succeed even with a small local model.
2. **Stable, predictable behaviour** — One dedicated place for “reminder-only” with a fixed tool set and prompt. No competition from dozens of other tools.
3. **Lower token/prompt load** — Fewer tools and no extra skills/plugins mean smaller context and lower cost.
4. **Clear UX** — “Use Reminder for reminders” is easy to explain; users get a reliable path without learning which friend “works” for reminders.
5. **Delivery stays correct** — We keep current delivery logic (send to the friend/context the reminder belongs to); Reminder is only a fallback when the system cannot determine the target.

So: **the idea is worth implementing.** Making **limited tools/skills/plugins and optimized history configurable per friend** gives a **framework** for this behaviour: Reminder and Finder are just examples; **users can customize** their own friends with restricted context too (§10).

---

## 9. Reusable design: special system friends (e.g. Reminder, Finder)

The same pattern can be applied to other **special system friends** that are dedicated to specific tasks with **limited context** so they **succeed more easily** (including with small local models). Reminder and Finder are **examples**; the real goal is a **framework** where this behaviour is **configurable per friend** (see §10).

### 9.1 The pattern (per-friend)

For a friend that uses **limited context** (Reminder, Finder, or any friend so configured):

- **Limited, predefined tools** — Inject only the tools needed for that friend’s task (e.g. Reminder: cron + reminder tools; Finder: search + file-handling tools).
- **Limited skills and plugins** — Only what’s needed for that task, or none. No full skill/plugin set.
- **Possibly less memory / optimized history** — They may not need a lot of long-term or cross-friend memory; inject only what's relevant (e.g. recent conversation, minimal RAG). That keeps context small and focused.
- **Short, focused system prompt** — e.g. “You are the Reminder assistant. You only schedule and list reminders.” or “You are the Finder assistant. You search and handle files. Use only the provided tools.”
- **Dedicated to one kind of task** — So the LLM has a small set of choices and is much more likely to pick the right tool and succeed.

So: **limited tools + limited skills/plugins + (optionally) limited/optimized history + short prompt → limited context → easier to succeed**, especially with small local models.

### 9.2 Examples: Reminder and Finder

- **Reminder:** Cron + reminder tools (and related skills/plugins), optimized history. Good at scheduling; other topics in that chat may not be so useful.
- **Finder:** Search + file-handling tools (and related skills/plugins). User talks to Finder for find files, list dirs, open/move/copy files, etc. Same benefit: small context, correct tool easy to select.

Reminder and Finder are just **one example** of how the framework can be used. The important step is to make this **configurable** (§10) so users can customize it too.

---

## 10. Configurable framework: limited tools/skills/plugins and optimized history per friend

If **limited tools, skills, plugins, and optimized history** are **configurable per friend**, we get a **framework** for this kind of behaviour. “Reminder” and “Finder” become **examples** (predefined or user-configured); **users can customize** their own friends with restricted context too.

### 10.1 What is configurable (per friend)

- **Tools** — Which tools to inject for this friend. Default: “all” (current behaviour). Option: a list of tool names (or a named preset like `reminder`, `finder`) so only those are injected.
- **Skills** — Which skills to inject. Default: “all”. Option: a list or preset so only those are injected.
- **Plugins** — Which plugins to inject. Default: “all”. Option: a list or preset.
- **History / memory** — How much and what to inject (e.g. full history vs. optimized: recent turns only, or minimal RAG). Default: same as today. Option: “optimized” or a policy (e.g. last N turns, no cross-friend memory).
- **System prompt** — Optional short, focused prompt for this friend (e.g. “You are the Reminder assistant. You only schedule and list reminders. Use only the provided tools.”).

When a friend has such a configuration, Core uses it when building context for that conversation: inject only the listed (or preset) tools/skills/plugins and apply the history/prompt policy. No separate code path per friend type — one **framework** that reads config and restricts context accordingly. Additional **pluggable** options (model routing, save policy, memory sources) are described in §10.4 (e.g. Note friend).

### 10.2 Where config can live

- **System friends** — Reminder, Finder, etc. can be defined with a preset or explicit list (e.g. in Core config or a system-friend registry). Every user gets them with that config.
- **User-defined friends** — In `user.yml`, Friends plugin, or a future “friend config” layer: per friend, optional fields such as `tools_preset: reminder`, or `tools: [remind_me, list_reminders]`, `history: optimized`, `system_prompt: "..."`. If present, Core uses them; otherwise “full” injection as today.

So: **Reminder** and **Finder** are just examples of friends that have this config set (e.g. `tools_preset: reminder` or `finder`). A user could add a custom friend “Notes” with only note-taking tools and optimized history, or reuse the same framework for their own “Reminder”-style friend with a different name.

### 10.3 Summary

- **Framework:** Per-friend configuration for **limited tools, skills, plugins, and optimized history** (and optional system prompt). One code path in Core: read config for the friend → inject only what’s allowed → build context.
- **Reminder and Finder:** Examples of friends that use this config (system-provided or user-configured). Not special-cased in logic; they just have a restricted injection config.
- **User customization:** Users can define or customize friends with the same mechanism — restricted tools/skills/plugins and optimized history — so they get “dedicated, limited context” behaviour for any friend they want.

### 10.4 Pluggable per-friend options (e.g. Note friend)

The same framework can support **pluggable** behaviour beyond tools/skills/plugins and history. Different friends can have different **model routing**, **privacy/save policy**, and **memory source**. Example: a **"Note"** friend with special requirements:

| Requirement | Meaning | Pluggable? |
|-------------|---------|------------|
| **1. Local model only** | This friend must use the local model; does not work in cloud-only mode. If the user is in cloud-only mode, Core can either refuse or show a message that "Note" requires local. | **Yes** — per-friend config e.g. `model_routing: local_only` (or `allowed_modes: [local, mix]`). Core reads it when handling this friend and routes/validates accordingly. |
| **2. Can save anything, no privacy problem** | User is okay saving anything in this context; the LLM should be told so it can suggest saving freely (e.g. notes, drafts). | **Yes** — per-friend config e.g. `save_policy: full` or `privacy: allow_save_anything`, and a **system-prompt line** (or context injection) so the LLM knows: e.g. "In this conversation the user allows saving any content; no privacy restrictions." |
| **3. Only Cognee/RAG memory, no MD memory** | This friend uses only Cognee (or RAG) memory for recall; do not use MD (markdown / long-term) memory. | **Yes** — per-friend config e.g. `memory_sources: [cognee]` or `memory_sources: [rag]` (and exclude `md`). Core, when building context for this friend, only injects from the allowed memory backends. |

So: **model routing**, **privacy/save policy**, and **memory source** can all be **pluggable** per friend. Implementation is the same pattern: a per-friend config (or preset like `note`) that Core reads and applies when building the request and context for that friend.

**Example "Note" friend config (conceptual):**

```yaml
# Example: Note friend
model_routing: local_only          # or allowed_modes: [local, mix]
save_policy: full                  # or privacy: allow_save_anything -> inject "user allows saving anything"
memory_sources: [cognee]           # or [rag]; exclude md
tools_preset: note                 # only note-related tools if desired
system_prompt: "You are the Note assistant. The user allows saving any content here; no privacy restrictions. Use only the provided tools and Cognee memory."
```

If we design the Core pipeline to read these keys from a **friend config** (or preset), then Reminder, Finder, Note, and any custom friend can mix and match: limited tools, optimized history, local-only, save policy, memory sources, and system prompt. All **pluggable** and composable.
