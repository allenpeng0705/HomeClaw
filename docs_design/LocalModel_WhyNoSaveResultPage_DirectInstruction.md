# Why the local model didn’t call save_result_page — and telling it to run directly

## 1. Problem

When we “prefer local for long-output turn” (after `document_read` or `run_skill`), the local model often does **not** call `save_result_page`. It may:

- Return **text** (reasoning + “I will generate…”) and a **placeholder** ` ```html ``` ` block instead of a real tool call.
- Emit a **stray** `&lt;tool_call&gt;` in content (so we treat it as “content before stray tag” and never get a structured `tool_calls`).
- Emit **malformed** tool calls (e.g. `document_read` with `path` = pasted document text or mixed instructions).

Fallbacks (e.g. “extract HTML from response and save”) only handle the case where HTML is already in the reply; they don’t fix the fact that the model **didn’t call the tool**. So we should understand **why** the local model didn’t call `save_result_page` and, when the previous step already “confirmed” the intent (e.g. `run_skill`), **tell the local model to run it directly**.

---

## 2. Why might the local model not call save_result_page?

### 2.1 Instruction is buried

- “Handling tool results” and “Your role this turn” are appended to a **long system** message.
- The run_skill result says: “You MUST in this turn: (1) document_read (2) generate (3) save_result_page…”.
- For the turn **after** run_skill, step (1) may already be done (document is in an earlier tool result). The model may not infer “skip (1), do (2) and (3) only”.
- So the “call save_result_page” part is one of several bullets in a long block; the model may default to “continue in text” instead of “emit a tool call”.

### 2.2 Model behavior (small/local)

- Smaller/local models (e.g. Qwen 3.5 9B) often prefer to **narrate** (“I will generate…”) or output a **code block** (e.g. “here is the HTML”) rather than emitting a **structured** `tool_calls` payload.
- If the local server or model uses a different tool format (e.g. literal `&lt;tool_call&gt;` in text), we may not parse it and treat it as “stray tag”, so we never execute `save_result_page`.

### 2.3 Context and ordering

- After several tool rounds, the conversation is long. The “you must call save_result_page” instruction lives in:
  - system (“Handling tool results”),
  - and in the **run_skill** tool result.
- The model’s “next token” behavior may favor continuing the **last** content (e.g. document or run_skill text) in natural language rather than starting a new tool call.

### 2.4 Ambiguity of “this turn”

- run_skill says “You MUST **in this turn**” do (1)(2)(3). If (1) was already done in a **previous** turn, the model might:
  - Try (1) again (wrong path or garbage in `path`),
  - Or do (2) in text and never do (3) as a tool call.

So the instruction doesn’t say: “(1) is already done; **only** do (2) and (3), and (3) must be a **tool call**.”

---

## 3. Principle: if the tool/skill is confirmed, tell the local model to run it directly

When we **know** the next required action (e.g. “generate HTML and call save_result_page”) because:

- the **previous** tool was `run_skill` (instruction-only, e.g. html-slides), or  
- the **previous** tool was `document_read` and the user asked for slides/report,

we should **not** rely only on long, generic instructions. We should add a **short, direct, context-aware** instruction that tells the local model exactly what to do in this turn (e.g. “call save_result_page with your generated HTML”).

---

## 4. Options to “tell local model to run it directly”

### Option A: Append a one-line “next action” to the last tool result

When we are about to call the local LLM for the long-output turn and `last_tool_name in ("document_read", "run_skill")`:

- **If last tool was run_skill:**  
  Append to the **last message** (the run_skill tool result) a single line, e.g.:  
  `→ Next: Generate the full HTML from the document content above, then call save_result_page(title='Slides', content=<your full HTML>, format='html'). Do not reply with only text—call the tool.`
- **If last tool was document_read:**  
  Append:  
  `→ Next: Call save_result_page(title='Slides', content=<your full HTML>, format='html') with the HTML you generate from the document above. Do not reply with only text—call the tool.`

**Pros:** Minimal change; the model sees it immediately after the tool result it must “respond” to.  
**Cons:** Modifies the tool result content; need to avoid breaking tool result parsing or display.

### Option B: Inject a synthetic “user” or “assistant” reminder message

Before calling the LLM for this turn, append a short **user** message (or a system line) that states only the next action, e.g.:

- “Reminder: In this turn you must call save_result_page(title='Slides', content=<full HTML>, format='html'). Do not reply with only a description or a code block—invoke the tool.”

**Pros:** Clear separation; doesn’t alter tool results.  
**Cons:** Adds an extra message; some models may treat it as a new user request and change behavior slightly.

### Option C: Context-aware “Handling tool results” for this turn only

When we route to **local** for the long-output turn and the last tool was `run_skill` or `document_read`, **replace or prepend** a short block in the system message for **this turn only**, e.g.:

- “This turn only: The document/skill step is done. Your task is to generate the full HTML and call save_result_page(title='...', content=<full HTML>, format='html'). Do not reply with only text—call the tool.”

**Pros:** Very explicit; scoped to this turn.  
**Cons:** More branching in prompt construction.

### Option D: When last tool was run_skill, rewrite the run_skill “instruction” for the save step

When the last tool result is from **run_skill** (instruction-only) and we are handing off to local for the long-output turn, we could **replace** the run_skill result text with (or append) a **short, single-purpose** instruction:

- “You have the document content above. Call save_result_page(title='Slides', content=<full HTML you generate>, format='html') and return the link. Do not reply with only text—call the tool.”

**Pros:** Removes ambiguity (“(1) document_read (2) generate (3) save_result_page”) and states only what’s left to do.  
**Cons:** Replacing tool result content might affect logging or other consumers; appending is safer.

---

## 5. Recommendation (for discussion)

- **Prefer Option A (append one line to the last tool result)** or **Option D (append a short, context-aware instruction to the run_skill result)** so the model sees a direct “next: call save_result_page” **right after** the tool result it is responding to.
- **Implement only when** we are actually routing to **local** for the long-output turn (`last_tool_name in ("document_read", "run_skill")` and we switched to local), so we don’t add noise for cloud or other flows.
- **Keep fallbacks** (extract HTML from response when it’s present) as a **safety net**, but treat “tell local to run it directly” as the **primary** fix so the model actually calls the tool instead of replying with text.

---

## 6. Implementation sketch

1. **Where:** In `core/llm_loop.py`, in the same block where we “prefer local for this turn” and inject “Handling tool results”, **and** when `last_tool_name in ("document_read", "run_skill")` and we are using the local model this turn:
   - Read the last message (role `tool`).
   - Append a single line to its `content` (or to a copy used only for this LLM call), e.g.:  
     `\n\n→ Next: Call save_result_page(title='Slides', content=<your full HTML>, format='html') with the HTML you generate. Do not reply with only text—call the tool.`
2. **Optional:** If the last tool was **run_skill**, make the line even more explicit:  
   “Document content is above. Your only task this turn: call save_result_page(..., format='html') with the full HTML. Do not reply with only text.”
3. **Testing:** Run the “summarize PDF → html slides” flow with local model for the long-output turn and confirm the model emits a proper `save_result_page` tool call instead of text + placeholder.

---

## 7. Fallback vs root cause

- **Fallback (extract HTML from response):** Only helps when the model already put HTML in the message. It does **not** address the root cause (model didn’t call the tool).
- **Root cause:** Instruction not prominent or context-aware enough; local model prefers text/code block over tool call.
- **Direct instruction:** Makes the required action (call save_result_page) explicit and immediate for the local model, so it’s more likely to “run it directly” instead of describing it.

We should implement the direct-instruction approach and keep the fallback as a secondary path.
