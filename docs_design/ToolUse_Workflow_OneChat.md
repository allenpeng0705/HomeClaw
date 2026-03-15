# Tool use workflow in one chat (e.g. read document → summarize → HTML slides)

This document explains how HomeClaw handles a **single user message** that requires **several tools in sequence** (e.g. “read this document, summarize it, and generate an HTML slide for me”) — in **one chat**, without the user sending multiple messages.

---

## Short answer

- **Available tools** are chosen **once** at the start of the turn (by intent router + config). For “read doc, summarize, HTML slide” the router typically gives categories like `read_document` and `create_slides`, so the model sees e.g. `document_read`, `file_read`, `run_skill` (with html-slides in the enum), `save_result_page`, etc.
- **Which tools actually run** is decided **step by step** by the LLM: each “round” the model can call zero or more tools; Core runs them, appends their results to the conversation, then calls the model again. The model keeps going until it stops calling tools and returns a final text reply.

So: **tool set = fixed at start; tool execution = step by step**, driven by the LLM each round.

---

## End-to-end flow (one user message)

1. **User sends one message**  
   e.g. “Read the file report.pdf, summarize it, and generate one HTML slide for me.”

2. **Intent router (one LLM call)**  
   Classifies the message (e.g. `read_document, create_slides`). Core then:
   - Filters **tools** to the union of those categories (e.g. document_read, file_read, run_skill, save_result_page, …).
   - Filters **skills** to the union (e.g. html-slides-1.0.0, ppt-generation-1.0.0).
   - Builds the **tool list** and **“Available skills”** block for the main model. This set is **fixed for the whole handling of this message**.

3. **Tool loop (main model, multiple rounds)**  
   Core enters a loop (up to `tools.max_tool_rounds`, default 30). Each iteration:

   - **Call the LLM** with the current conversation: user message + any previous assistant messages + tool results.
   - **If the LLM returns tool_calls** (e.g. `document_read`, then later `run_skill`, then `save_result_page`):
     - Core **executes each** tool and appends each result as a `tool` message.
     - Then Core **loops again**: calls the LLM with the updated conversation (including the new tool results).
   - **If the LLM returns no tool_calls** (only text):
     - Core treats that as the **final reply** and exits the loop.

So the model does **not** “select all tools at once” for execution. It selects **which tool(s) to call in this round**; after seeing their results, it selects the next tool(s) in the next round, and so on.

---

## Example: “Read report.pdf, summarize, generate one HTML slide”

Rough sequence:

| Round | Input to LLM | LLM output | Core action |
|-------|----------------------------|------------|-------------|
| 1 | User: “Read report.pdf, summarize, generate one HTML slide” | Tool call: `document_read(path="report.pdf")` | Run document_read; append result (document text) to conversation. |
| 2 | User message + Assistant (tool_calls) + Tool (document content) | Tool call: `run_skill(skill_name='html-slides', …)` (with content from context or args) | Run html-slides skill; append result (HTML) to conversation. |
| 3 | … + Tool (HTML from skill) | Tool call: `save_result_page(title="…", content=…, format="html")` | Run save_result_page; append result (e.g. link) to conversation. |
| 4 | … + Tool (link) | No tool_calls; content: “Here’s your slide: [link]…” | Use this as the final reply; exit loop and return to user. |

So in **one chat** you get: **one** intent-router run → **one** fixed tool/skill set → **several** rounds of “LLM chooses tool(s) → Core runs them → LLM sees results and chooses again” until the model responds with text only.

---

## Details that matter for this workflow

- **Same model for the whole chain**  
  The same main model is used for every round of the tool loop for that message, so “read → summarize → slides” stays in one chain (no switching model mid-task unless a fallback is triggered).

- **Prompt nudge after tool results**  
  When the last message is a tool result, Core injects a short “Handling tool results” block so the model is reminded to:
  - Use the actual tool output (e.g. document content) for the next step.
  - For HTML slides: if the tool result is document content and the user asked for slides, **call** `run_skill(html-slides)` in this turn, not just say “I will generate…”.

- **Multiple tools in one round**  
  The model can return **several** tool_calls in one response (e.g. `document_read` and something else). Core runs **all** of them and appends **all** results, then does the next LLM call. So “step by step” is “per round”; one round can still run multiple tools.

- **When the loop stops**  
  The loop stops when the LLM returns **no** tool_calls (only content), or when routing/plugin sends the reply, or when a file-view link is used as the reply, or when `max_tool_rounds` is reached.

---

## Summary

| Question | Answer |
|----------|--------|
| Are all required tools selected once at the start? | **Yes** for *which* tools are **available** (by intent router + category union). |
| Are tools executed all at once or step by step? | **Step by step**: each round the LLM chooses which tool(s) to call; Core runs them, adds results, and calls the LLM again until it replies with text only. |
| One chat, one user message? | **Yes.** One user message can trigger many rounds of tool use and one final reply. |

So for “read one document, summarize it, and generate one HTML slide” in **one chat**: HomeClaw fixes the tool/skill set once (read_document + create_slides), then the model **step by step** calls e.g. `document_read` → `run_skill(html-slides)` → `save_result_page`, and finally returns the slide link in a single reply.
