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
