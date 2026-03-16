# User interaction in DAG and planner flows

Flows sometimes need **user input** before continuing: confirmation (send/cancel), choosing one of several options, or free text. This doc describes patterns and a generic design. See also **PlannerExecutorAndDAG.md** §3 (DAG) and §2 (planner–executor).

---

## 1. Current pattern: implicit continuation (e.g. send_email)

**How it works today:**

1. The DAG runs in **one turn** and produces a response that **asks the user to reply** (e.g. draft + "Reply **send** to send, or **cancel** to discard").
2. The flow **stops**; that response is shown to the user.
3. On the **next turn**, the user says "send" or "cancel". We **do not re-run the full DAG**. Instead:
   - **Before** calling the DAG, the core loop checks: "Is this the send_email flow? Is the user message a confirmation (send/cancel)? Does the **last assistant message** look like our draft (To:/Subject:/Body: + Reply send/cancel)?"
   - If **cancel** → return "Email cancelled." and skip the DAG.
   - If **send** → parse the draft from the last assistant message, call `run_skill(imap-smtp-email, smtp.js, send …)` with parsed To/Subject/Body, return the result.

**Pros:** No new state store; works with existing conversation history.  
**Cons:** Logic is **flow-specific** (send_email confirmation is hard-coded in `llm_loop`). Adding another "confirm then do X" flow would require more special cases unless we generalize.

---

## 2. Generic approach: interaction steps + pending flow state

To support **arbitrary** "pause for user input, then continue" without one special case per flow:

### 2.1 New step type: `interaction`

A step that does **not** run a tool and does **not** produce output in the same turn. It:

- **Pauses** the DAG at that step index.
- **Stores** "pending flow" state (see below).
- **Returns** a prompt to the user (from the previous step's result, or from a fixed `prompt` in the step).

Config sketch:

```yaml
# Example: flow that pauses for confirmation
steps:
  - tool: file_read
    args_from: { path: [flow_config:contacts_path] }
  - output_only: [llm_compose_email_from_step_1]
    append: "\n\n---\nReply **send** to send, or **cancel** to discard."
  - interaction:
      type: confirm          # or select | text
      prompt_from_step: "2"   # show step 2 result as the question
      choices: [send, cancel] # for confirm; for select: list of options
      on_choice:
        send: step_4
        cancel: end
  - tool: run_skill
    args_from:
      skill_name: "imap-smtp-email"
      script: "smtp.js"
      args: [send, "--to", [result_of_step_2_parsed_to], ...]
```

### 2.2 Pending flow state

When the executor hits an `interaction` step, it:

- **Does not** run the rest of the DAG in this turn.
- Saves **pending flow state** somewhere the next request can read it, e.g.:
  - **Session / request-scoped store** keyed by `(user_id, session_id)` or `(user_id, friend_id)`.
  - Or a **token** in the assistant response that the client sends back (e.g. `pending_flow_id` or encoded flow + step index).

State shape (minimal):

- `flow_id` (e.g. `send_email`)
- `flow` (full flow dict or reference)
- `step_index` (next step to run after interaction, e.g. 3)
- `step_results` (results of steps 1..N so far)
- Optional: `interaction_step_spec` (type, choices, prompt_from_step)

### 2.3 Next turn: resume instead of starting from scratch

Before running the intent router / DAG as usual:

1. **Load** pending flow state for this user/session (if any).
2. If state exists and the **current user message** can be interpreted as the interaction response (e.g. "send"/"cancel" for confirm, or one of the options for select):
   - **Resume** the DAG from the step **after** the interaction step.
   - Pass the user's reply as **input** for that step (e.g. store as `step_results["interaction"]` or resolve a new source `user_interaction_reply`).
   - Run the remaining steps (e.g. `run_skill` for "send").
   - **Clear** pending state.
   - Return the DAG result as the response.
3. If state exists but the message is **not** a valid choice (e.g. user says something else): either re-show the prompt and keep pending state, or clear state and fall back to normal routing.
4. If no pending state, run the router and DAG as today (possibly starting a new flow that may later pause at an interaction step).

### 2.4 Where to store state (implementation options)

| Option | Where | Pros | Cons |
|--------|--------|------|------|
| **A. In-memory (Core)** | Dict keyed by `(user_id, session_id)` in Core or a small "flow state" module | Simple; no DB | Lost on restart; not shared across instances |
| **B. Request metadata** | Client (companion/channel) stores `pending_flow_id` or token and sends it with the next message | Stateless Core | Requires client support; token size/encoding |
| **C. Conversation / memory** | No explicit state; infer from last assistant message (current send_email pattern) | No new infra | Only works for one pattern per flow; not generic "select 1 of N" |

For a **generic** solution, A or B is needed so the executor can "resume from step 4 with `user_choice=send`" without re-running steps 1–2.

---

## 3. Config schema for interaction steps (proposed)

### Confirm (binary choice)

```yaml
- interaction:
    type: confirm
    prompt_from_step: "2"      # step whose output is the message we showed
    choices: [send, cancel]
    on_choice:
      send: step_4
      cancel: end
```

### Select (one of N options)

```yaml
- interaction:
    type: select
    prompt: "Which report do you want? (1) Summary (2) Full (3) Cancel"
    options: [summary, full, cancel]
    on_choice:
      summary: step_4
      full: step_5
      cancel: end
```

### Text (free-form)

```yaml
- interaction:
    type: text
    prompt_from_step: "2"
    # next step gets user message as args_from: [user_interaction_reply]
```

**New args_from source for "after interaction" steps:**  
`user_interaction_reply` or `user_choice` — value is the normalized choice (for confirm/select) or raw message (for text), so later steps can use it.

---

## 4. Planner–Executor and user interaction

The **planner** could output a step like `{ "id": "3", "tool": "ask_user", "arguments": { "prompt": "Send or cancel?", "choices": ["send", "cancel"] } }`. The executor would:

- Treat `ask_user` as a **pause**: store pending plan + step index, return the prompt to the user.
- On the next turn: if pending plan exists and user reply matches a choice, resume the executor from the next step, with the choice stored (e.g. as `step_3_result`) for placeholder replacement in later steps.

Same **pending state** idea as DAG: keyed by user/session, store plan + step index + step_results; on resume, run from the next step with `user_choice` available as a placeholder value.

---

## 5. Summary

| Need | Current approach | Generic approach |
|------|-------------------|------------------|
| **Single confirmation** (e.g. send/cancel) | Implicit: last message is draft; next message "send"/"cancel" handled in llm_loop with flow-specific code | Interaction step + pending state; resume next turn with `user_choice` |
| **Select one of N options** | Not supported generically | `interaction` type `select` + `on_choice` → step or end |
| **Free text then continue** | Not supported | `interaction` type `text`; next step uses `user_interaction_reply` |

**To implement the generic approach:**

1. Add `interaction` step handling in `run_dag` (detect step, save state, return prompt, exit).
2. Add a small **pending flow store** (e.g. in Core, keyed by user/session).
3. In `llm_loop`, before running the DAG: check for pending state; if present and user message is a valid response, resume DAG from stored step with user reply as input; otherwise run router/DAG as today.
4. Add args_from source `user_interaction_reply` / `user_choice` for steps that run after an interaction.
