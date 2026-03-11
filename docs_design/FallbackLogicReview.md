# Fallback logic review (no tool_calls path)

When the LLM returns **no tool_calls**, Core runs a series of fallbacks so the user still gets a useful response. This doc lists them in execution order and what you see in logs.

---

## 1. Log message you’ll see first

```
[tools] model returned no tool_calls; unhelpful=<bool> auto_invoke_count=<N> run_force_include=<bool>
```

- **unhelpful**: True if the model’s text reply looks unhelpful (short, “no tool”, “I can’t”, errors, etc.).
- **auto_invoke_count**: Number of entries in `force_include_auto_invoke` (from rules + built-in list-folder).
- **run_force_include**: True if we will run one of those tools (when unhelpful **or** any rule has `always_run`).

---

## 2. Fallback order (when model returns no tool_calls)

### A. Force-include auto_invoke (run_force_include == True)

**Condition:** `force_include_auto_invoke` is non-empty **and** (reply is unhelpful **or** any rule has `always_run`).

**Sources of force_include_auto_invoke:**

1. **Config rules** (`skills_force_include_rules` in skills config): pattern match → add `{ tool, arguments, always_run? }`.
2. **Skill triggers** (SKILL.md `trigger.patterns` + `auto_invoke.script`): adds `run_skill` with script/args.
3. **Built-in list-folder**: if the query matches list-folder phrases (“documents folder”, “list files”, “目录”, etc.) we append `folder_list` with inferred path (`documents`, `downloads`, … or `.`) and `always_run=True`.

**What runs:** We iterate `force_include_auto_invoke` and run the **first** tool that exists in the registry. As soon as one runs and returns a non-empty result, we use that as the response and **break** (no further fallbacks in this block).

**Log:** `[tools] fallback auto_invoke <tool_name> (model did not call tool)`

**If none ran or all failed:** We keep the model’s text reply (`content_str`).

---

### B. Only when run_force_include is False

So we only reach B if we did **not** run a force-include tool (e.g. no rules matched, or reply was “helpful” and no `always_run`).

#### B1. Remind-me fallback

**Condition:** Query matches remind_me intent (`_infer_remind_me_fallback`), `remind_me` is in registry, we didn’t already run remind_me this turn.

**Log:** `[tools] fallback remind_me (model did not call tool)`

**On failure or missing time:** We may show a clarification message (“When would you like to be reminded?”).

#### B2. Cron/scheduling fallback

**Condition:** Reply still unchanged **and** query looks like scheduling (“every day at 9”, etc.) **and** `cron_schedule` in registry; we didn’t already run cron_schedule this turn.

**Log:** `[tools] fallback cron_schedule (model did not call tool)`

#### B3. Route / run_skill fallback

**Condition:** Reply still unchanged **and** reply is “unhelpful” (short or “no”/“sorry”) **and** `_infer_route_to_plugin_fallback(query)` returns a route (e.g. open URL, run_skill).

- If tool is `run_skill`: run it, use result or “Done.”
- Else if `route_to_plugin` in registry: run it with the inferred route.

**Log:** `[tools] fallback run_skill (model did not call tool)` or `[tools] fallback route_to_plugin (model did not call tool)`

#### B4. Summarize-document fallback

**Condition:** Reply still unchanged **and** registry has `file_find` and `document_read` **and** query has “summarize” and “.pdf” or “.docx” **and** model didn’t already return something that looks like success (link, “已生成”, etc.).

We run `file_find` then `document_read`, then a second LLM call to summarize.

**Log:** `[tools] fallback summarize document (model did not call tool)`

#### B5. List-directory fallback (phrase-based)

**Condition:** Reply still unchanged **and** registry has `folder_list` **and** query matches `list_dir_phrases` (“list files”, “documents folder”, “目录”, etc.).

We infer path (e.g. `documents`) and run `folder_list(path=...)`, then format the result as a user-friendly list.

**Log:** `[tools] fallback folder_list (model did not call tool)`

**If none of B1–B5 applied:** We use the model’s text reply (`content_str`).

---

## 3. Other log lines you may see

- **Scheduling but no tool:**  
  `TAM did not set schedule: user asked for scheduling/reminder but model returned no tool_calls ...`

- **List-folder intent but no tool_calls:**  
  `User asked to list a folder (...) but model returned no tool_calls; running folder_list via force_include ...`  
  (This is when we **did** run folder_list via force_include, not the B5 phrase fallback.)

- **Fallback failures (DEBUG):**  
  `Fallback auto_invoke <tool> failed: ...`  
  `Fallback remind_me failed: ...`  
  `Fallback cron_schedule failed: ...`  
  `Fallback run_skill failed: ...`  
  `Fallback route_to_plugin failed: ...`  
  `Fallback summarize document failed: ...`  
  `Fallback folder_list failed: ...`

---

## 4. Review points (logic and safety)

1. **Order:** Force-include runs first and can “win” with a single successful tool. So for “what files in documents folder”, if list-folder was added to `force_include_auto_invoke` with `always_run=True`, we run `folder_list` there and never need the B5 phrase fallback. Both paths infer the same path (e.g. `documents`).
2. **Overlap:** List-folder is in **both** (A) force_include (built-in) and (B5) phrase fallback. A runs only when `run_force_include` is True (unhelpful or always_run). So for a “helpful” long reply that didn’t call a tool, we might still run folder_list in B5 if the query matches list_dir_phrases.
3. **Safety:** All fallback executions are in try/except; failures are logged and we keep the model reply or a safe message. No fallback is allowed to crash Core.
4. **Double run:** We never run the same tool twice in the “no tool_calls” block: force_include runs one tool and breaks; B1–B5 each have conditions (e.g. “reply still unchanged”) so we don’t re-run a tool that already ran in A.

---

## 5. Paste your log

If you paste the exact log lines (including the `[tools]` and any fallback messages), we can map them to the steps above and confirm which fallback ran and why.
