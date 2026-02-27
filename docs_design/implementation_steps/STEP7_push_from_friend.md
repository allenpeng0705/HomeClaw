# Step 7: Push from_friend — done

**Design ref:** [UserFriendsModelFullDesign.md](../UserFriendsModelFullDesign.md) implementation step 7 and §8.

**Goal:** Ensure every push (APNs/FCM and WebSocket push event) includes **from_friend** (friend_id or `"HomeClaw"`) so the Companion app can route notifications to the correct friend chat. Ensure TAM (reminders, cron) and inbound fallback pass the correct `from_friend` when calling `deliver_to_user`. Update [CompanionPushNotifications.md](../CompanionPushNotifications.md) to document `from_friend` in the payload.

---

## 1. What was already in place

- **core/core.py** `deliver_to_user(user_id, text, ..., from_friend="HomeClaw")` — already accepts `from_friend` and passes it to WebSocket payload and to `push_send.send_push_to_user`.
- **base/push_send.py** `send_push_to_user(..., from_friend="HomeClaw")` — already passes `from_friend` to APNs and FCM.
- **base/apns_send.py** and **base/fcm_send.py** — already add `from_friend` to payload (custom key / data map).
- **core/core.py** inbound fallback — already uses `content.get("from_friend") or "HomeClaw"` for WS push and for `send_push_to_user`.

---

## 2. What was implemented (Step 7)

### 2.1 TAM (core/tam.py)

- **send_reminder_to_channel:** Now passes `from_friend=params.get("friend_id") or "HomeClaw"` so cron/reminder callers can specify which friend the reminder is from (e.g. when job params include `friend_id`). Default remains `"HomeClaw"`.
- **schedule_one_shot** (in-memory fallback when run_time invalid): Calls `deliver_to_user(..., source="reminder", from_friend="HomeClaw")` explicitly.
- **_run_one_shot_and_remove:** Calls `deliver_to_user(..., source="reminder", from_friend="HomeClaw")` explicitly. (Step 10 will add `friend_id` to one-shot storage and pass it as `from_friend` when firing.)

All calls are inside existing try/except; no new code path raises.

### 2.2 CompanionPushNotifications.md

- **§2.2** — Noted that `deliver_to_user` accepts `from_friend` and is used by reminders, cron, inbound, and proactive delivery.
- **§2.3** — Documented **from_friend** in APNs and FCM payloads; updated Companion behaviour to route using `from_friend` to the correct friend chat.

---

## 3. Robustness

- TAM: `from_friend` is derived with `.strip()` and default `"HomeClaw"` so None or empty is safe. No new exceptions; deliver_to_user already normalizes and never raises.
- Payload: APNs/FCM already cap `from_friend` length (e.g. 128 chars) in apns_send/fcm_send.

---

## 4. Files touched

| File | Change |
|------|--------|
| **core/tam.py** | send_reminder_to_channel: pass from_friend from params; schedule_one_shot fallback and _run_one_shot_and_remove: pass from_friend="HomeClaw". |
| **docs_design/CompanionPushNotifications.md** | Document from_friend in deliver_to_user, payload (APNs/FCM), and Companion routing. |

---

## 5. Review

- **Logic:** All deliver_to_user call sites now pass from_friend (explicit or from params). Inbound already did. Payload and doc updated. ✓
- **Robustness:** Default "HomeClaw"; params.get("friend_id") with strip; no new code path raises. ✓

**Step 7 is complete.** Next: Step 8 (Chat and sessions: (user_id, friend_id)).
