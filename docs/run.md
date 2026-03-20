# Run

How to start HomeClaw Core and connect to it.

---

## Start Core

```bash
python -m main start
```

This starts Core (port **9000** by default) and an interactive CLI. You can also run Core without the CLI: `python -m core.core`.

**Verify:** `curl -s http://127.0.0.1:9000/ready` should return 200. Run `python -m main doctor` to check config and LLM connectivity.

---

## Connect

| Method | How |
|--------|-----|
| **Companion App** | Set Core URL to `http://127.0.0.1:9000` in the app. [Details →](companion-app.md) |
| **WebChat** | `python -m channels.run webchat` → http://localhost:8014 |
| **Telegram** | `python -m channels.run telegram` |
| **Discord** | `python -m channels.run discord` |
| **CLI** | Built into `python -m main start` |

Set `CORE_URL` in `channels/.env` and add allowed users in `config/user.yml`.

---

## Watch logs

**PowerShell:**

```powershell
Get-Content logs\core_debug.log -Wait -Tail 50
```

**Mac / Linux:**

```bash
tail -f logs/core_debug.log
```

---

## Windows console tips

If running Core from Command Prompt, the console may pause with "More?" when the buffer fills. Fixes:

1. Set `log_to_console: false` in `config/core.yml` (all logs go to `logs/core_debug.log`).
2. Set `silent: true` in `config/core.yml` (reduces console output).
3. Run in **PowerShell** instead of CMD.
4. Increase CMD screen buffer height (right-click title bar → Properties → Layout → set Height to 9999).
