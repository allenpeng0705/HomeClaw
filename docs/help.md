# Help

Troubleshooting and where to find more.

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
