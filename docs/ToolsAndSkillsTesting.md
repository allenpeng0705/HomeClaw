# Testing tools and skills: example messages that trigger tools

When **`use_tools: true`** in `config/core.yml`, the main LLM receives the list of built-in tools and chooses when to call them based on your message. Below are **example messages** that typically trigger each tool (or tool group). The model may combine tools (e.g. `time` then answer, or `browser_navigate` then `browser_snapshot`).

**Note:** The LLM is not guaranteed to use a tool for every matching phrase; it depends on context and model behavior. These examples are meant to give you a reliable starting set for testing.

### Troubleshooting: Browser tools (Playwright)

If **browser_navigate** (or open baidu.com / any URL) fails with an error about a missing executable or Playwright:

1. **Install the Playwright browser (Chromium)** — the Python package alone is not enough:
   ```bash
   python -m playwright install chromium
   ```
   Use the same Python environment that runs Core (e.g. your venv).

2. **On Linux**, if Chromium still fails to launch (missing libs), install system dependencies:
   ```bash
   python -m playwright install --with-deps chromium
   ```
   This may require `sudo` only for this one-time dependency install; do **not** run Core itself with `sudo`.

3. **Do not run Core with `su` or `sudo`** to fix browser permission. Running Core as root is a security risk. The fix is to install Chromium for the user that runs Core (step 1–2 above). Browsers are installed under that user’s cache (e.g. `~/.cache/ms-playwright` on Linux).

4. To show the browser window when testing locally, set in **`config/core.yml`** under `tools:`:
   ```yaml
   browser_headless: false
   ```

5. **"Chromium not found" even after install:** Playwright installs browsers **per Python environment**. Use the **same** Python (and venv) to run `playwright install` as the one that runs Core. Example: if you start Core with `./venv/bin/python` or `python core/main.py`, run `./venv/bin/python -m playwright install chromium` (or activate that venv first, then `python -m playwright install chromium`). The error message will show the path Playwright is looking for so you can confirm which env is used.

---

## Time and system

| Tool | Example messages that often trigger it |
|------|----------------------------------------|
| **time** | "What time is it?", "Current date and time?", "What's the time in UTC?" |
| **platform_info** | "What platform are you running on?", "Python version?", "Are you on Linux or Windows?" |
| **cwd** | "What's the current working directory?", "Where is the Core running from?" |
| **session_status** | "What's my session id?", "Who am I in this chat?" |

---

## Scheduling (TAM / cron)

| Tool | Example messages that often trigger it |
|------|----------------------------------------|
| **cron_schedule** | "Remind me every day at 9am", "Schedule a reminder at 10:00 every Monday", "Run every 2 hours" |
| **cron_list** | "List my scheduled reminders", "What cron jobs do I have?", "Show my reminders" |
| **cron_remove** | "Cancel reminder job X", "Remove the 9am daily reminder" (after you have a job_id from cron_list) |

---

## Sessions and chat history

| Tool | Example messages that often trigger it |
|------|----------------------------------------|
| **sessions_transcript** | "Show our conversation", "What did we talk about?", "Give me the last 10 messages" |
| **sessions_list** | "List my chat sessions", "What sessions exist for this user?" |
| **sessions_send** | "Send 'hello' to session abc123", "Ask the other session: what is 2+2?" (needs session_id or app_id+user_id) |
| **sessions_spawn** | "Run a quick task: summarize 'long text here'", "Use a sub-agent to translate this to French" |

---

## Memory (when `use_memory: true`)

| Tool | Example messages that often trigger it |
|------|----------------------------------------|
| **memory_search** | "What do you remember about me?", "Search your memory for 'meeting with John'", "Do you remember my preferences?" |
| **memory_get** | "Get memory by id xyz" (after you have an id from memory_search) |

---

## Web and browser

| Tool | Example messages that often trigger it |
|------|----------------------------------------|
| **fetch_url** | "Fetch https://example.com and summarize", "Get the content of this URL", "What's on this page?" (static HTML) |
| **browser_navigate** | "Open https://example.com in the browser", "Go to google.com", "Navigate to this URL" (full browser; use for JS pages) |
| **browser_snapshot** | After navigate: "What buttons are on the page?", "List clickable elements", "Get the page structure" |
| **browser_click** | After snapshot: "Click the Login button", "Click element with selector [data-homeclaw-ref=\"0\"]" |
| **browser_type** | After snapshot: "Type 'hello' into the search box", "Fill the email field with user@example.com" |
| **web_search** | "Search the web for latest news about X", "What's the weather in Paris?" (requires BRAVE_API_KEY or config) |

---

## Files and folders

| Tool | Example messages that often trigger it |
|------|----------------------------------------|
| **folder_list** | "List files in the current directory", "What's in the config folder?", "Show contents of ." |
| **file_read** | "Read the file config/core.yml", "Show me the contents of README.md" |
| **file_write** | "Write 'hello' to file test.txt", "Create a file notes.txt with content ..." |
| **file_edit** | "In file X replace 'old' with 'new'", "Change the first occurrence of 'foo' to 'bar' in config.yml" |
| **apply_patch** | "Apply this diff to file X" (when you provide a unified diff) |

Paths are relative to **`tools.file_read_base`** in `config/core.yml` (default: current directory).

**"Directory restrictions" / "path must be under the configured base directory":** File tools only allow reading/writing under **`tools.file_read_base`** (default: `.`, i.e. the directory Core was started from). To fix: set **`file_read_base`** in `config/core.yml` to a directory that **contains** the files you want Core to read. Examples: use `"."` to allow the project folder only; use an **absolute path** (e.g. `/Users/you/Documents` or `C:\Users\you\Documents`) to allow that folder and its subfolders. Restart Core after changing. Paths you ask for (e.g. in "read report.pdf") must be **relative** to that base (e.g. `reports/report.pdf` if base is `/Users/you/Documents`).

---

## Shell and processes

| Tool | Example messages that often trigger it |
|------|----------------------------------------|
| **exec** | "Run the command: date", "Execute: whoami", "Run ls -la" (only if the command name is in **tools.exec_allowlist**, e.g. `date`, `whoami`, `echo`, `pwd`, `ls`, `cat`) |
| **process_list** | "List background processes", "What jobs are running?" |
| **process_poll** | "Check status of job abc123", "Did my background job finish?" |
| **process_kill** | "Kill job abc123", "Stop the background process" |

---

## Images and other

| Tool | Example messages that often trigger it |
|------|----------------------------------------|
| **image** | "Describe the image at path screenshots/foo.png", "What's in this image? [url or path]" (requires a vision-capable LLM) |
| **echo** | "Echo back: hello world" (for testing that tools are invoked) |
| **env** | "What is the value of HOME?", "Get environment variable PATH" |
| **models_list** | "List available models", "What LLMs are configured?" |
| **agents_list** | "List agents" |
| **run_skill** | "Run the script run.sh from skill weather-help", "Execute main.py in skill example" (when skills with scripts/ are loaded) |
| **channel_send** | Used by the model when it wants to send an extra message to the same channel (e.g. "I'll send you the link in a follow-up message"). |
| **webhook_trigger** | "POST to https://my-server.com/webhook with body {\"event\":\"test\"}" |

---

## Quick test set

Try these in order to quickly confirm tools are working:

1. **"What time is it?"** → `time`
2. **"List files in the current directory"** or **"What's in the config folder?"** → `folder_list`
3. **"Open https://example.com"** → `browser_navigate` or `fetch_url`
4. **"Echo back: tools work"** → `echo`
5. **"Run the command: date"** (if `date` is in `tools.exec_allowlist`) → `exec`
6. **"Show our conversation"** → `sessions_transcript`
7. **"Remind me every day at 9am"** → `cron_schedule` (if TAM/orchestrator is enabled)

Ensure **`use_tools: true`** in `config/core.yml` and, for **exec**, that the command name (e.g. `date`, `ls`) is listed in **`tools.exec_allowlist`**.
