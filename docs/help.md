# Help

Troubleshooting and where to find more.

---

## Where to find things

| You want to… | Go here |
|--------------|--------|
| **Install** HomeClaw | [Install](install.md) — Mac/Linux: `bash install.sh`. Windows: `.\install.ps1` or `install.bat`. |
| **Get started** (run Core, chat) | [Getting started](getting-started.md) — full walkthrough from install to chatting. |
| **Use the Companion App** | [Companion App](companion-app.md) — build from `clients/HomeClawApp/`; set Core URL in Settings. |
| **Open the Portal** | [Portal Guide](portal.md) — run `python -m main portal`, open http://127.0.0.1:18472. |
| **Connect from anywhere** | [Remote Access](remote-access.md) — Pinggy, Cloudflare Tunnel, ngrok, Tailscale. |
| **Add AI friends / family** | [Friends & Family](friends-and-family.md) — create AI personalities, add family members. |
| **Set up Telegram / Discord** | [Channels](channels.md) — connect HomeClaw to Telegram, Discord, Slack, WebChat. |
| **Use Cursor / Claude Code** | [Coding with HomeClaw](coding-with-homeclaw.md) — drive IDEs from your phone. |

---

## Check config and LLM

```bash
python -m main doctor
```

Runs checks and suggests fixes for config and LLM connectivity.

---

## Common issues

| Issue | What to try |
|-------|-------------|
| **Permission denied** | Add your `user_id` (e.g. `telegram_<chat_id>`) to `config/user.yml` under `im` (or `email` / `phone`). |
| **Core not reachable** | Ensure Core is running (`python -m core.core` or `python -m main start`) and `channels/.env` has the correct `CORE_URL`. |
| **Channel connection error** | Start the channel process (e.g. `python -m channels.run webchat`). For full channels (Matrix, etc.), the channel must be running so Core can POST replies to `/get_response`. |
| **Web search "unconfigured"** | Set `TAVILY_API_KEY` (or another provider) in the environment or in `config/core.yml` under `tools.web.search`. Or use DuckDuckGo fallback (`fallback_no_key: true`). |
| **Browser tools fail** | Install Playwright browser: `python -m playwright install chromium`. Use the same Python env as Core. |
| **"Local LLM unreachable" / WinError 64** | Core can be running while the **model server** (e.g. on port 5023) is not. The error means the connection to the LLM server was dropped or the server is not running (crashed, not started, or restarted). **Fix:** Start or restart the model server, or restart Core so it starts the main LLM (llama.cpp). On Windows, "network name is no longer available" is the same. **Timeouts** are separate — you would see "timed out after Xs"; increase `llm_completion_timeout_seconds` in config if needed. |
| **LLM works for 1–2 rounds then fails** | The main LLM process (llama.cpp) may have **crashed or exited**. After the next failed request, Core logs **"Main LLM process has exited"** with PID, exit code, and the process **stderr** (last 500 chars) so you can see why it died. Check Core logs for that line and the stderr snippet; restart Core to restart the model server. |

---

## Docs in the repo

- **README.md** — Overview, quick start, channels, plugins, skills.
- **HOW_TO_USE.md** — Step-by-step setup and usage.
- **Design.md** — Architecture and components.
- **Channel.md** — Channel usage and config.
- **docs_design/** — PluginsGuide, SkillsGuide, MemoryAndDatabase, ToolsDesign, MultiUserSupport, RemoteAccess, etc.

---

## GitHub

- **Repo:** [https://github.com/allenpeng0705/HomeClaw](https://github.com/allenpeng0705/HomeClaw)
- Open an **issue** for bugs or feature requests.
