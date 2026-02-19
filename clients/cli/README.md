# HomeClaw CLI

Lightweight command-line client for **HomeClaw Core**: chat, status, and sessions. One entrypoint, a few subcommands (more can be added; see **docs_design/OpenClawCLIInvestigationAndHomeClawRoadmap.md** for how OpenClaw’s CLI is structured and our roadmap).

## Setup

```bash
cd clients/cli
pip install -r requirements.txt
```

## Commands

| Command   | Description |
|-----------|-------------|
| **chat**  | Send a message to Core (POST /inbound) and print the reply. |
| **status** | Check Core reachability and session count (GET /api/sessions). |
| **sessions** | List sessions (GET /api/sessions). Use `--json` for raw JSON. |
| **pair**  | Print a QR code (and URL) with Core URL + API key for the companion app to scan (one-tap connect). Requires `qrcode` (e.g. `pip install qrcode[pil]`). |

## Config file (optional)

The CLI reads **Core URL** and **API key** from (in order): `--url` / `--api-key`, then env (`HOMECLAW_CORE_URL`, `HOMECLAW_API_KEY`), then config file. Config file paths (first found wins):

- **Current directory:** `.homeclaw` (JSON: `{"url": "http://...", "api_key": "..."}`).
- **User config:** `~/.config/homeclaw/cli.json` (same format).

So you can put URL and API key in `~/.config/homeclaw/cli.json` and omit `--url` / `--api-key` for most commands.

## Usage

```bash
# Chat (Core at default http://127.0.0.1:9000)
python homeclaw_cli.py chat "Hello, what time is it?"

# Status and sessions
python homeclaw_cli.py status
python homeclaw_cli.py sessions
python homeclaw_cli.py sessions --json

# Pair: show QR for mobile app (run on the machine where Core is reachable, e.g. same LAN or Tailscale)
python homeclaw_cli.py pair
# Or with explicit URL (e.g. your Tailscale URL so the phone can reach Core)
python homeclaw_cli.py --url http://100.x.x.x:9000 pair

# Custom Core URL / API key (env or flags)
export HOMECLAW_CORE_URL=http://192.168.1.10:9000
export HOMECLAW_API_KEY=your-secret-key
python homeclaw_cli.py chat "Hello"
python homeclaw_cli.py --url http://192.168.1.10:9000 --api-key your-key chat "Hello"
```

## Global options (all commands)

| Option     | Description                          | Default              |
|------------|--------------------------------------|----------------------|
| `--url`    | Core base URL                        | Env `HOMECLAW_CORE_URL`, then config file, then `http://127.0.0.1:9000` |
| `--api-key` | API key when Core auth is enabled  | Env `HOMECLAW_API_KEY` or config file |

## Chat options

| Option     | Description           | Default |
|------------|-----------------------|---------|
| `--user-id` | user_id sent to Core | `cli`   |

## Optional: install as command

From repo root you can run without `python`:

```bash
# Unix/macOS
chmod +x clients/cli/homeclaw_cli.py
./clients/cli/homeclaw_cli.py chat "Hello"

# Or add to PATH / symlink
ln -s "$(pwd)/clients/cli/homeclaw_cli.py" /usr/local/bin/homeclaw
homeclaw chat "Hello"
```

See **../README.md** for client connectivity (Tailscale, Cloudflare, etc.).
