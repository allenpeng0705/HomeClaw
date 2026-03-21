# Portal Guide

The **Portal** is HomeClaw's web-based control panel. Use it to configure your LLM, manage users, start Core and channels, and install skills — all from your browser.

---

## Open the Portal

```bash
python -m main portal
```

The Portal runs at **http://127.0.0.1:18472** by default. If you ran the install script, it opens automatically when setup completes.

You can also access the Portal from the **Companion App**: go to **Settings → Core setting (Portal)** to open it in a WebView.

---

## First-time setup

When you open the Portal for the first time:

1. **Create an admin account** — Pick a username and password. This is for Portal login only (not your AI chat identity).
2. **Dashboard** — After login, you land on the Dashboard with shortcuts to common tasks.

---

## What you can do in the Portal

### Configure your LLM

The most important setting: which AI model to use.

1. Go to **Manage Settings** (or **core.yml editor**)
2. Under **Cloud Models**, find or add your model (e.g. Gemini, OpenAI, DeepSeek)
3. Set the **API key** for that model
4. Set **main_llm** to point to your chosen model (e.g. `cloud_models/Gemini-2.5-Flash`)
5. Save and restart Core

**Local models:** If you want to run a model on your own hardware, configure entries under **local_models** and point `main_llm` to one of them. See [Models](models.md) for details.

### Manage users

Under **User Management** (or **user.yml editor**):

- **Add users** — Each person who talks to HomeClaw needs an entry with a `name`, `id`, and their platform identities (`im` for Telegram/Discord, `email` for email channel, etc.)
- **Set permissions** — Control who can access admin features
- **Add friends** — Give each user a list of AI friends (see [Friends & Family](friends-and-family.md))

### Start Core

From the Dashboard or the **Start Core** button:

- Start the Core engine (equivalent to `python -m main start`)
- Monitor Core status
- Restart Core after config changes

### Start channels

Launch channels directly from the Portal:

- **WebChat** — Opens a browser chat at http://localhost:8014
- **Telegram** — Starts the Telegram bot (requires bot token in config)
- **Discord** — Starts the Discord bot (requires bot token)

See [Channels](channels.md) for full setup instructions.

### Install guide

The Portal includes a built-in **Guide to Install** that walks you through:

- Checking Python and Node.js versions
- Installing dependencies
- Setting up llama.cpp (for local models)
- Downloading GGUF model files

### Run doctor

Check your environment from the Portal or command line:

```bash
python -m main doctor
```

This verifies config files, workspace folders, llama-server availability, and LLM connectivity.

---

## Accessing the Portal remotely

The Portal runs on `127.0.0.1` (localhost only). To access it from another device:

- **Same network:** Run `python -m main portal --host 0.0.0.0` (if supported) or set up port forwarding on your router for port 18472.
- **From the Companion App:** If Core is reachable (e.g. via a [tunnel](remote-access.md)), the Companion App can open the Portal through Core's API.
- **Via tunnel:** If you already have a Cloudflare Tunnel or Pinggy tunnel for Core (port 9000), you can set up an additional tunnel for the Portal (port 18472), or use the Companion App's built-in Portal access.

---

## Portal vs Companion App vs config files

| Task | Portal | Companion App | Config files |
|------|--------|--------------|-------------|
| Edit core.yml / user.yml | Yes | Yes (Manage Core) | Yes (text editor) |
| Start Core | Yes | No | `python -m main start` |
| Start channels | Yes | No | `python -m channels.run <name>` |
| Install skills (ClawHub) | No | Yes | `clawhub install <skill>` |
| Chat with AI | No | Yes | CLI: `python -m main start` |
| Add friends | Via user.yml | Via friend list | Edit user.yml |

Use whichever method is most convenient. All three manage the same config files; changes from one are visible to the others.

---

## Tips

- **Portal won't open?** Check that nothing else is using port 18472. Override with `PORTAL_PORT=18480 python -m main portal`.
- **Changes not taking effect?** Restart Core after editing config. Some settings (like `main_llm`) require a Core restart.
- **Lost your Portal password?** Delete the Portal's auth database (check `database/` folder) and restart the Portal to re-create the admin account.
