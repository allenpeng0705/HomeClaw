# Run-skill in-process vs subprocess

This doc describes how Python skill scripts are run (in-process vs subprocess), and how **run_skill_py_in_process_skills** selects which run in-process, and how we try to avoid breaking Core.

---

## 1. Subprocess by default; in-process only when listed

When a skill's folder name is in **run_skill_py_in_process_skills** (config list):

- **Every** `.py` / `.pyw` skill script is run the same way: in Core’s process, in a **thread** (so the event loop is not blocked).
- For all of them we:
  - Set `sys.argv`, `os.chdir(skill_folder)`, and put the script’s directory first on `sys.path`.
  - Restore `sys.argv`, cwd, and `sys.path` in `finally`.
  - Redirect stdout/stderr to buffers and restore them in `finally`.
  - Run the script with `exec(code, globals_dict)` and catch exceptions so they don’t kill the thread.
- Optional **pre-import** (e.g. `google.genai`, PIL) only helps skills that use those packages; other skills are unaffected. No per-skill branching.

So: **subprocess for all skills by default**; **in-process only for skills named in run_skill_py_in_process_skills**.

---

## 2. Safeguards so running a script doesn’t break Core

We **cannot fully guarantee** that a script won’t affect Core, because it runs in the same process. We do the following to limit risk:

| Safeguard | What it does |
|-----------|----------------|
| **Run in a thread** | Script runs in `run_in_executor` (thread). Exceptions are contained in that thread; we catch and turn them into stderr text. |
| **Timeout** | `run_skill_timeout` (config) is applied; we `wait_for(..., timeout=timeout)`. A stuck script doesn’t block Core forever. |
| **State restore** | We save and restore `sys.argv`, `os.getcwd()`, `sys.path`, `sys.stdout`, `sys.stderr` in `finally`, so the script shouldn’t leave Core in a bad state. |
| **Exception handling** | We catch `Exception` and `SystemExit` (and optionally `BaseException`) and write to the script’s stderr buffer; we don’t re-raise into the event loop. |

**Remaining risks:**

- A script (or a C extension it loads) could crash the **process** (e.g. segfault, `os._exit()`), which would bring down Core.
- A script could **pollute** `sys.modules` or other global state; we don’t reset that.
- A script could use a lot of **CPU or memory** and slow or starve Core.

So: in-process is **same env, reliable imports**, but **not isolated**. For untrusted or risky skills, use **subprocess** instead.

---

## 3. Default: subprocess so Core is never broken

- **Default: subprocess:** All `.py` skills run in a **subprocess** unless listed in **run_skill_py_in_process_skills**. A bug, crash, or `os._exit()` in the script only affects that subprocess, not Core. **Core never breaks** from a skill script.
- **In-process allowlist:** Add a skill's **folder name** (e.g. `image-generation-1.0.0`) to **run_skill_py_in_process_skills** only if you trust that skill and need the same process (e.g. same env for imports). Same process = risk that a bad script can affect Core.
- **Script allowlist:** Use **run_skill_allowlist** so only specific script names can run; that limits which scripts can run at all.

Summary: **Subprocess by default** = isolated, never break Core. **In-process** = only for skills listed in run_skill_py_in_process_skills; use only for trusted skills.

---

## 4. Sending output images to companion or channel

**Any** skill or tool whose output includes images can send them back to the user via channel or companion app (not only the image-generation skill):

1. **Convention:** The script (or any run_skill/tool) prints one or more lines `HOMECLAW_IMAGE_PATH=<absolute path>` (e.g. after saving each file). The run_skill executor parses all such lines and sets `request.request_metadata["response_image_paths"]` (list).
2. **Core** then includes those paths in the response:
   - **Async channels (request queue):** `response_data["images"] = [path, ...]` and `response_data["image"] = first path`. Channels that support outbound image (e.g. Matrix, WeChat) can send the first or all.
   - **Sync /inbound (and WebSocket):** The handler returns images as **data URLs** in the JSON (`"images": ["data:image/png;base64,...", ...]`, and `"image"` for the first) so remote clients (e.g. companion app) can display them.
3. **Companion app:** `POST /inbound` response can include `"images"` (list of data URLs). The companion displays all of them in the chat when present.

**Other files** (e.g. PDF, documents) can be handled in a similar way later (e.g. a convention like `HOMECLAW_FILE_PATH=...` and channel/companion support for file attachments).

---

## 5. No cache of tool or API responses — if generation “stops working”

**Core does not cache** run_skill results or LLM/API responses. Each request runs tools and the model again. So “it worked before, now it doesn’t” is not due to a stale cache in HomeClaw.

**If you cleared chat histories only:** The model gets no prior turns; skills are still loaded (from the skills vector store or, if that’s empty, from disk). Image generation can still work as long as the image skill is in the prompt (vector search or force-include rule).

**If you cleared the skills vector store** (e.g. `POST /api/skills/clear-vector-store` or `POST /api/testing/clear-all`): Vector search returns no hits. Core then falls back to `load_skills()` from disk (alphabetical by folder name) and takes the first `skills_max_in_prompt` (e.g. 5). The image skill might not be in that set. **Restart Core** so skills are re-synced at startup (`skills_refresh_on_startup: true`); then vector search works again and “generate image” queries should retrieve the image skill.

**Force-include rule:** In `config/core.yml`, `skills_force_include_rules` can force the image skill into the prompt when the user query matches a pattern (e.g. “generate an image”, “create an image”, “draw a picture/image”). Use one of those phrases to ensure the skill is included even if vector search didn’t return it.

**To debug:** Check Core logs to see whether `run_skill` was invoked for the image skill and what the script’s stdout/stderr was. Confirm the script’s API key and that the output file is actually written (the script only reports success when the file exists and has size &gt; 0).
