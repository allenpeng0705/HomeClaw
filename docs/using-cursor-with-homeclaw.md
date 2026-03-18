# Using Cursor with HomeClaw

You can have **HomeClaw** open a project in Cursor, run Cursor’s agent and see the result, or run shell commands on your dev machine from any channel (Telegram, Companion, WebChat, etc.).

---

## Quick summary: Cursor via Companion app

1. **Run the Cursor Bridge** on the machine where Cursor is installed:  
   `python -m external_plugins.cursor_bridge.server` (port 3104).
2. **Add the Cursor friend** in `config/user.yml` for your user: under `friends:` add  
   `- name: Cursor` and `preset: cursor`, then restart Core.
3. **In the Companion app:** tap **Cursor** in the friend list and chat. Say e.g. “open D:\myproject in Cursor”, “run Cursor agent to add tests and show me the result”, or “run npm test in Cursor”. You get the reply (and any command/agent output) back in the same chat.

Make sure HomeClaw Core can reach the bridge (same machine: `http://127.0.0.1:3104`; other machine: set `config.base_url` in `plugins/CursorBridge/plugin.yaml` to the bridge URL).

---

**Main features:**

- **Open a project/folder in Cursor** — e.g. “open my project in Cursor” or “open D:\repos\MyApp in Cursor”. Cursor opens so you can chat with the agent there.
- **Run Cursor’s agent and see results** — e.g. “have Cursor agent fix the bug and show me the output” or “run Cursor agent to add tests”. The bridge runs the CLI agent and returns the output to your channel.
- **Run a command and see results** — e.g. “run npm test in Cursor”. You get the command output back in the channel.

## Cursor friend (Companion app)

An **AI preset friend** named **Cursor** is available so you can use Cursor from the Companion app like being on the computer. This friend is dedicated to the Cursor Bridge: it only sees the Cursor Bridge plugin and a small set of tools (open project, run agent, run command), so it stays focused and works like a remote Cursor assistant.

**To add the Cursor friend** for a user, edit `config/user.yml` and add under that user’s `friends:` list:

```yaml
- name: Cursor
  preset: cursor
```

Restart Core (or reload config if your setup supports it). The Cursor friend will appear in the Companion app’s friend list. Tap it to chat; say e.g. “open D:\myproject in Cursor”, “run Cursor agent to add unit tests and show me the result”, or “run npm test in Cursor”. The preset is defined in `config/friend_presets.yml` (preset `cursor`); you can customize `system_prompt` or other options there.

## What you need

1. **Cursor Bridge** — A small HTTP server on the machine where Cursor (and your projects) run. It opens projects, runs the Cursor CLI agent, or runs shell commands.
2. **Cursor Bridge plugin in HomeClaw** — Under `plugins/CursorBridge/`. Core routes to it when you say things like “open project in Cursor” or “run Cursor agent to …”.

## Setup (one-time)

### 1. Run the Cursor Bridge on your dev machine

From the HomeClaw repo (or wherever you have the bridge code):

```bash
# Default port 3104
python -m external_plugins.cursor_bridge.server
```

Optional:

- **Port:** `CURSOR_BRIDGE_PORT=3104` (default 3104).
- **Default project directory for commands:** `CURSOR_BRIDGE_CWD=D:\path\to\your\project`

Keep this running (or run it in the background / as a service) whenever you want to use “run in Cursor” from HomeClaw.

### 2. Make sure HomeClaw can reach the bridge

- **HomeClaw Core on the same machine:** No change. `plugins/CursorBridge/plugin.yaml` uses `base_url: "http://127.0.0.1:3104"`.
- **HomeClaw Core on another machine (e.g. server, other PC):** Edit `plugins/CursorBridge/plugin.yaml` and set `config.base_url` to your dev machine’s URL, e.g. `http://192.168.1.100:3104` or your Tailscale hostname. Restart Core after changing.

## Use it

From any channel or the Companion app, say for example:

- **Open project:** “Open D:\myproject in Cursor.” / “Open my project in Cursor.” (use a path you set or that the LLM can infer.)
- **Run agent and see results:** “Run Cursor agent to add a README with installation steps and show me the result.” / “Have Cursor fix the failing test and show the output.”
- **Run command:** “Run npm test in Cursor.” / “In Cursor run pip install -r requirements.txt.”

HomeClaw routes to the Cursor Bridge; the bridge opens the project in Cursor, runs the agent, or runs the command and returns the result to you.

## More details

- **Bridge code and options:** `external_plugins/cursor_bridge/README.md`
- **Design (contract, security):** `docs_design/HomeClaw_Uses_Cursor_And_Traefik_Design.md` (Cursor section)
