# Run

How to start HomeClaw Core and channels.

---

## 1. Start Core

From the project root:

```bash
python -m core.core
```

Or run the interactive CLI (Core runs in a background thread; you chat in the terminal):

```bash
python -m main start
```

Core listens on **port 9000** by default (`config/core.yml`).

---

## 2. Start a channel

In another terminal, start a channel so you can talk to the assistant:

| Channel   | Command                          | Typical URL / use        |
|----------|-----------------------------------|---------------------------|
| **WebChat** | `python -m channels.run webchat` | http://localhost:8014    |
| **Telegram** | `python -m channels.run telegram` | Your Telegram bot         |
| **Discord**  | `python -m channels.run discord`  | Your Discord bot          |
| **CLI**      | (use `python -m main start` above) | Terminal only            |

Set **`channels/.env`** with `CORE_URL` (e.g. `http://127.0.0.1:9000`) and any bot tokens. Add allowed users in **`config/user.yml`**.

---

## 3. Quick test

1. Start Core: `python -m core.core` or `python -m main start`.
2. Start WebChat: `python -m channels.run webchat`.
3. Open http://localhost:8014 and send a message. Ensure your `user_id` is in `config/user.yml`.

---

## 4. Doctor (check config and LLM)

```bash
python -m main doctor
```

Checks config and LLM connectivity and suggests fixes. See [Help](help.md) for troubleshooting.

---

## 5. Console output and blocking (Windows)

When you run Core from **Command Prompt** (`cmd`), you may see a lot of log lines and then the app **stops and waits for you to press Space** (“More?”). That happens because (1) Core logs heavily when `silent: false`, and (2) when the CMD screen buffer is full, Windows pages output and blocks until you press a key.

**Ways to fix it:**

1. **Send all logs only to the log file (no console)**  
   In **`config/core.yml`** set:
   ```yaml
   log_to_console: false
   ```
   Then nothing is written to the console; all logs go to **`logs/core_debug.log`**. Monitor with e.g. `Get-Content logs\core_debug.log -Wait -Tail 50` (PowerShell) or `tail -f logs/core_debug.log` (Git Bash/WSL). The app will not block on Space.

2. **Reduce console logging**  
   In **`config/core.yml`** set:
   ```yaml
   silent: true
   ```
   Then Core will log only INFO-level messages to the console (less output, no need to press Space). Full logs still go to `logs/core_debug.log` (or similar).

3. **Increase CMD screen buffer** (so “More?” doesn’t appear)  
   In the Command Prompt window: right‑click the title bar → **Properties** → **Layout** tab → **Screen Buffer Size** → set **Height** to a large value (e.g. **9999**). Click OK. Then restart Core.

4. **Run in PowerShell**  
   PowerShell doesn’t page the same way. Run Core in PowerShell instead of CMD:
   ```powershell
   python -m main start
   ```
   or
   ```powershell
   python -m core.core
   ```

5. **Redirect output to a file** (no console output, no blocking)  
   ```cmd
   python -m main start > logs\core-console.txt 2>&1
   ```
   Logs go to `logs\core-console.txt`; the console stays empty and the app won’t block on Space.

6. **Run the app quietly and monitor the log with a tail tool**  
   Run Core with `silent: true` (or redirected output) so the app doesn’t flood the console. In a **second terminal**, watch the log file with a tail-like tool:
   - **PowerShell:**  
     ```powershell
     Get-Content logs\core_debug.log -Wait -Tail 50
     ```
     (Shows the last 50 lines and keeps appending new lines.)
   - **Git Bash / WSL:**  
     ```bash
     tail -f logs/core_debug.log
     ```
   So you run the app in one window (no blocking) and follow logs in the other.

---

## 6. Tail / follow the log file (Windows and Mac)

To watch the Core log file live in a second terminal:

**Windows (PowerShell)**  
From the project root:
```powershell
Get-Content logs\core_debug.log -Wait -Tail 50
```
- `-Wait` keeps the command running and shows new lines as they are written.  
- `-Tail 50` shows the last 50 lines first (change to e.g. `100` if you want more).  
- Stop with **Ctrl+C**.

**Mac (and Linux)**  
From the project root:
```bash
tail -f logs/core_debug.log
```
- `-f` follows the file (new lines appear as they are written).  
- Stop with **Ctrl+C**.  
- Optional: `tail -F logs/core_debug.log` keeps following even if the file is rotated (recreated).
