# HomeClaw CLI

Command-line tool to send messages to **HomeClaw Core** and print the reply.

## Setup

```bash
cd clients/cli
pip install -r requirements.txt
```

## Usage

```bash
# Send a message (Core at default http://127.0.0.1:9000)
python homeclaw_cli.py chat "Hello, what time is it?"

# Custom Core URL
export HOMECLAW_CORE_URL=http://192.168.1.10:9000
python homeclaw_cli.py chat "Hello"

# Or pass URL per run
python homeclaw_cli.py chat --url http://192.168.1.10:9000 "Hello"

# If Core has auth_enabled, set API key
export HOMECLAW_API_KEY=your-secret-key
python homeclaw_cli.py chat "Hello"

# Or pass API key per run
python homeclaw_cli.py chat --api-key your-secret-key "Hello"
```

## Options (chat command)

| Option     | Description                          | Default              |
|------------|--------------------------------------|----------------------|
| `--url`    | Core base URL                        | `HOMECLAW_CORE_URL` or `http://127.0.0.1:9000` |
| `--api-key` | API key when Core auth is enabled  | `HOMECLAW_API_KEY`   |
| `--user-id` | user_id sent to Core                | `cli`                |

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
