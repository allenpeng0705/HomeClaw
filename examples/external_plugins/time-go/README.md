# Time Plugin (Go)

External Time plugin for HomeClaw, implemented in **Go** (standard library only).

- **Port:** 3112
- **Endpoints:** `GET /health`, `POST /run` (body = PluginRequest JSON, response = PluginResult JSON)

## Run

```bash
cd examples/external_plugins/time-go
go run .
# Or: go build -o time-go && ./time-go
```

## Register with Core

With Core running (default http://127.0.0.1:9000) and the plugin server running:

```bash
chmod +x register.sh
./register.sh
```

Or set `CORE_URL` / `PLUGIN_BASE` if needed:

```bash
CORE_URL=http://127.0.0.1:9000 PLUGIN_BASE=http://127.0.0.1:3112 ./register.sh
```

Then ask: "What time is it in Tokyo?" or "List timezones."
