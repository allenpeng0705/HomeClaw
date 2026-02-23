# Quote Plugin (Node.js)

External Quote plugin for HomeClaw, implemented in **Node.js** (no framework; built-in `http` only).

- **Port:** 3111
- **Endpoints:** `GET /health`, `POST /run` (body = PluginRequest JSON, response = PluginResult JSON)

## Run

```bash
# From project root or from this directory
cd external_plugins/quote-node
npm start
# Or: node server.js
```

## Register with Core

With Core running (default http://127.0.0.1:9000) and the plugin server running:

```bash
node register.js
# Or: npm run register
```

Or with curl:

```bash
curl -X POST http://127.0.0.1:9000/api/plugins/register \
  -H "Content-Type: application/json" \
  -d @- << 'JSON'
{
  "plugin_id": "quote-node",
  "name": "Quote Plugin (Node.js)",
  "description": "Get a random inspirational quote, or by topic.",
  "health_check_url": "http://127.0.0.1:3111/health",
  "type": "http",
  "config": { "base_url": "http://127.0.0.1:3111", "path": "run", "timeout_sec": 10 },
  "capabilities": [
    { "id": "get_quote", "name": "Get random quote", "description": "Returns a random quote.", "parameters": [], "post_process": true, "post_process_prompt": "Add one short inspiring sentence.", "method": "POST", "path": "/run" },
    { "id": "get_quote_by_topic", "name": "Get quote by topic", "description": "Quote by topic.", "parameters": [{"name": "topic", "type": "string", "required": true}], "post_process": false, "method": "POST", "path": "/run" }
  ]
}
JSON
```

Then ask: "Give me an inspirational quote" or "Quote about success."
