# Design discussion: system friend “Reminder” per user (cron/reminder focus)

**Status:** Discussion / design only — no implementation yet.

**Target:** When the user uses the **Reminder** friend, reminder/cron should **succeed much more easily**, even with a **small local model**. We achieve this by **not injecting too much** into the context — only reminder/cron tools and related bits — so the model has a small, focused set to choose from.

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

- **Idea:** One system friend “Reminder” per user. For this friend we **do not** inject all skills, tools, and plugins — **only** what is used for Reminder (cron + reminder).
- **Benefits:** Minimal injected surface for the Reminder chat → correct tool easy to select → more stable cron/reminder behaviour; clear place to *talk about* reminders; delivery keeps current path (Reminder only as fallback when target unknown); reusable pattern for other system friends.
- **Main decisions:** (1) How the friend appears in the list (injected vs configured), (2) fixed id (e.g. `"Reminder"`), (3) exact list of tools/skills/plugins to inject for Reminder only. **Delivery:** keep current path and logic; use Reminder only as fallback when the system cannot determine where to send.

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

So: **the idea is worth implementing.** We are not adding many system friends, but having **this kind of design** — a special system friend with limited, predefined tools/skills/plugins and possibly reduced memory injection — is a reusable pattern.

---

## 9. Reusable design: special system friends (e.g. Finder)

The same pattern can be applied to other **special system friends** that are dedicated to specific tasks with **limited context** so they **succeed more easily** (including with small local models).

### 9.1 The pattern

For a **special system friend** (Reminder, Finder, or future ones):

- **Limited, predefined tools** — Inject only the tools needed for that friend’s task (e.g. Reminder: cron + reminder tools; Finder: search + file-handling tools).
- **Limited skills and plugins** — Only what’s needed for that task, or none. No full skill/plugin set.
- **Possibly less memory** — They may not need a lot of long-term or cross-friend memory; inject only what's relevant (e.g. recent conversation, minimal RAG). That keeps context small and focused.
- **Short, focused system prompt** — e.g. “You are the Reminder assistant. You only schedule and list reminders.” or “You are the Finder assistant. You search and handle files. Use only the provided tools.”
- **Dedicated to one kind of task** — So the LLM has a small set of choices and is much more likely to pick the right tool and succeed.

So: **special system friends = limited tools + limited skills/plugins + (optionally) limited memory + short prompt → limited context → easier to succeed**, especially with small local models.

### 9.2 Example: a “Finder” friend

- **Purpose:** Search and handle files. User talks to “Finder” when they want to find files, list dirs, open/move/copy files, etc.
- **Injection:** Only file/search-related tools (and any file-related skills/plugins if needed). No reminder tools, no browser, no other domains. Optionally minimal memory (e.g. current session only).
- **Benefit:** Same as Reminder — small context, correct tool easy to select, **succeeds much more easily** even with a small local model. User has a clear place for “file and search” tasks.

We are **not** committing to adding many system friends. The point is: **we should have this kind of design.** When we introduce a special system friend (Reminder first, maybe Finder or others later), we apply the same rules:

- Limited, predefined tools (and skills/plugins) for that friend.
- Optionally reduced memory injection so context stays small.
- Dedicated to specific tasks with limited context → easier to succeed.

### 9.3 Summary

We are not intent on adding many system friends. The value is in **having this design**: special system friends that use **limited, predefined tools, skills, and plugins** and **optionally less memory**, so they are **dedicated to specific tasks with limited context** and **succeed more easily**, including with small local models. Reminder is the first instance; a Finder (search/files) or others could follow the same pattern if we choose to add them.
