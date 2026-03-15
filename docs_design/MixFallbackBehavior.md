# Mix / hybrid router fallback behavior

When both a local and a cloud model are configured (hybrid/mix mode), the Core can **switch to the other model** in two situations. This doc explains why you see logs like "tool result was error-like, retrying with cloud" or "first model failed, retrying with local", and what they mean.

---

## 1. "tool result was error-like, retrying with cloud" (or "retrying with local")

**When it happens**

- The **first model** (e.g. local) ran a **tool** and the **tool’s return value** was classified as "error-like".
- The Core does **not** show that tool result to the user. Instead it starts a **second LLM call** with the **other** model (e.g. cloud), using the same conversation (including the tool result in context), so the other model can try to answer or pick a better tool.

**How "error-like" is decided**

- Implemented in `tool_result_looks_like_error()` (e.g. in `core/services/tool_helpers.py` and fallback).
- The **tool result string** is checked for patterns such as:
  - `"error:"` at the start or in the first 200 chars
  - `"not found"`, `"wasn't found"`, `"file not found"`
  - `"path is required"`, `"no entries"` + `"directory"`
  - A few other file/path/instruction patterns.

So any tool that returns a short message containing those phrases is treated as error-like and triggers the **mix retry** (switch to the other model for the next turn).

**Typical example (your logs)**

- User asked: **"images目录下有哪些文件"** (what files are in the images directory).
- **Local model** chose **`exec`** with a **Unix-style command** (e.g. `ls -la images/`).
- On **Windows**, that command fails (e.g. "ls is not recognized" or the exec tool returns `"Error: command not found: ls"` or stderr with "error").
- That tool result is **error-like** → Core sets "use other model next turn".
- On the **next loop iteration** you see: **"tool result was error-like, retrying with cloud"**.
- So the **cloud** model is called with the same messages (including the failed exec result), in the hope it might call a better tool (e.g. `folder_list`) or reply in text.

**What it means**

- The **first model’s tool use** led to something that looks like an error.
- The system is **giving the other model a chance** with the same context, instead of showing that error to the user.

---

## 2. "first model failed, retrying with local" (or "retrying with cloud")

**When it happens**

- The model we **just switched to** (or the one we started with in the no-tool path) **failed**:
  - **Network/server**: connection refused, timeout, etc. (e.g. cloud endpoint at 127.0.0.1:4005 not running).
  - Or the LLM **returned empty** and the config allows fallback.
- The Core then **retries once** with the **other** model (e.g. if cloud failed, retry with local).

**Typical example (your logs)**

- After "retrying with cloud", the **cloud** request was made to something like `127.0.0.1:4005` and got **"The remote computer refused the network connection"**.
- So the **cloud** call is treated as failed → you see **"first model failed, retrying with local"**.
- The **local** model is then called again. If it returns **empty** (no text, no tool call), the user may see the generic **"Done. What would you like to do next? (已完成。还需要什么？)"** or the last usable content.

**What it means**

- The **current** model (the one we just tried) **failed** (connection/error or empty).
- The system is **falling back** to the other model so the request can still be answered.

---

## Summary for your scenario

| Step | What happened |
|------|----------------|
| 1 | User asked a simple file-listing question ("images目录下有哪些文件"). |
| 2 | **Local** model chose **exec** with a Unix command (`ls` etc.) instead of **folder_list**. |
| 3 | **Exec** failed on Windows → tool result was **error-like** (e.g. "Error: ..." or "not recognized"). |
| 4 | Core decided: **don’t show this error**; try the **other** model → **"tool result was error-like, retrying with cloud"**. |
| 5 | **Cloud** request failed (e.g. connection refused to 127.0.0.1:4005) → **"first model failed, retrying with local"**. |
| 6 | **Local** was called again; it returned **empty** → user saw **"Done. What would you like to do next?"** (and we now add the route label, e.g. [Local · fallback]). |

So the "jump to fallbacks" was:

1. **First fallback**: tool result looked like an error → retry with the **other** model (cloud).
2. **Second fallback**: that model **failed** (e.g. not running) → retry with **local** again.

**How to improve behavior**

- Prefer **folder_list** / **file_find** for "what files in X" on the platform you use; the local model sometimes chooses **exec** with shell commands that fail on Windows.
- Ensure the **cloud** endpoint is running and reachable if you want the "error-like" retry to actually use cloud.
- System prompt / tool descriptions can stress using **folder_list** for listing directories on the current OS instead of **exec** with `ls`.
