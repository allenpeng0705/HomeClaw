# Step 10: TAM one-shot reminders (user_id, friend_id) — done

**Design ref:** [UserFriendsModelFullDesign.md](../UserFriendsModelFullDesign.md) implementation step 10.

**Goal:** Store one-shot reminders with (user_id, friend_id). When a reminder fires, deliver to user_id with **from_friend = friend_id** so Companion/UI shows which friend set the reminder. Payload includes friend_id for UI. Never crash Core.

---

## 1. What was implemented

### 1.1 memory/database/models.py

- **TamOneShotReminderModel:** Added **friend_id** column (String, nullable=True). Used when reminder fires as from_friend. NULL = "HomeClaw" (backward compat).

### 1.2 memory/database/database.py

- **Migration:** On create_tables (SQLite), ALTER TABLE to add **friend_id** to `homeclaw_tam_one_shot_reminders` if missing. No crash; column may already exist.

### 1.3 memory/tam_storage.py

- **add_one_shot_reminder(..., friend_id=None):** Persists friend_id (normalized with str().strip(); try/except so invalid types do not raise; store None when missing).
- **load_one_shot_reminders:** Returned dicts include **friend_id** (getattr(r, "friend_id", None)). Per-row try/except: one bad row (missing attr or exception) is skipped and logged at debug; others are returned so Core never crashes.

### 1.4 core/tam.py

- **schedule_one_shot(..., friend_id=None):** Normalize friend_id with str().strip() or "HomeClaw" in try/except; pass to add_one_shot_reminder (store only when not default "HomeClaw"); pass to task lambda for _run_one_shot_and_remove.
- **_load_one_shot_reminders_from_db:** For each row, try: read run_at, id, message, user_id, channel_key, friend_id; normalize _fid in try/except; build task and schedule_fixed_task; on exception skip row and log debug. So one bad row does not prevent loading others; Core never crashes.
- **_run_one_shot_and_remove(..., friend_id=None):** Compute from_friend = str(friend_id or "").strip() or "HomeClaw" in try/except; call deliver_to_user(..., from_friend=from_friend); call send_reminder_to_channel(..., params with friend_id=from_friend).
- **schedule_job_from_intent (execute_now):** Resolve friend_id from request (friend_id or app_id); pass to schedule_one_shot.
- **record_event(..., friend_id=None):** Pass friend_id to schedule_one_shot when scheduling day_before / on_day reminders.

### 1.5 tools/builtin.py

- **remind_me:** Resolve friend_id from context (friend_id or app_id); pass to tam.schedule_one_shot(..., friend_id=friend_id).
- **_record_date_executor:** Resolve friend_id from context; pass to tam.record_event(..., friend_id=friend_id).

---

## 2. Robustness and safety

- **DB:** New column nullable; migration in try/except; existing rows valid (NULL → "HomeClaw" when firing).
- **tam_storage:** friend_id normalized in try/except; invalid type → fid = None; no raise. load_one_shot_reminders: per-row try/except so one bad DB row is skipped.
- **tam.py:** All friend_id usage wrapped in try/except; default "HomeClaw"; _load_one_shot_reminders_from_db: per-row try/except so one bad row does not abort load; deliver_to_user and send_reminder_to_channel already accept from_friend/friend_id in params.
- No new code path raises; existing try/except and defaults preserved.

---

## 3. Files touched

| File | Change |
|------|--------|
| **memory/database/models.py** | friend_id column on TamOneShotReminderModel. |
| **memory/database/database.py** | Migration: add friend_id to homeclaw_tam_one_shot_reminders. |
| **memory/tam_storage.py** | add_one_shot_reminder(friend_id); load_one_shot_reminders include friend_id in dict; safe normalize. |
| **core/tam.py** | schedule_one_shot(friend_id); _run_one_shot_and_remove(friend_id, from_friend); _load_one_shot_reminders_from_db pass friend_id to task; schedule_job_from_intent and record_event pass friend_id. |
| **tools/builtin.py** | remind_me and record_date pass friend_id from context to TAM. |

---

## 4. Review

- **Logic:** One-shot reminders stored with friend_id; on fire deliver with from_friend=friend_id; load from DB passes stored friend_id to task. ✓
- **Backward compat:** NULL friend_id in DB → "HomeClaw" when firing; default "HomeClaw" when not passed. ✓
- **Robustness:** Safe str(), try/except everywhere; no new raises. ✓

**Step 10 is complete.** Next: Step 11 (Channels: route to (user_id, HomeClaw)).
