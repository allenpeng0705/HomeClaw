# Plugins

Plugins add focused capabilities: weather, news, email, custom APIs, browser automation, and more. One plugin = one feature. **Built-in and external plugins** make HomeClaw **extensible and more powerful**.

**Want to write your own?** See [Writing plugins and skills](writing-plugins-and-skills.md) for a guide to building plugins (built-in and external) and skills, with examples and a future plugin/skill marketplace.

---

## Built-in plugins (Python)

- Live in `plugins/<Name>/` with **plugin.yaml** (id, description, capabilities), **config.yml** (API keys, defaults), and **plugin.py** (class extending `BasePlugin`). Core discovers them at startup.
- Examples: Weather, News, Mail. The LLM sees the plugin list and calls **route_to_plugin(plugin_id)** when the user intent matches.

---

## External plugins (any language)

- **External plugins can be written in any language**—Node.js, Go, Java, Python, or whatever you prefer. There are many tools and ecosystems you can leverage.
- The **system plugin** **homeclaw-browser** (in `system_plugins/homeclaw-browser`) is **one external plugin**, written in **Node.js**. It provides WebChat, browser automation, canvas, and nodes. You can run it with Core via **system_plugins_auto_start** in `config/core.yml`.
- **How it works:** Run your plugin as a separate **HTTP server** that implements:
  - `GET /health` → 2xx
  - `POST /run` (or your path) → body = PluginRequest JSON, response = PluginResult JSON.
- **Register** with Core: `POST http://<core>:9000/api/plugins/register` with plugin id, name, description, `health_check_url`, `type: "http"`, `config` (base_url, path, timeout_sec), and `capabilities`. After registration, Core routes to your server like built-in plugins.

**Examples:** Small samples in `examples/external_plugins/` — **Python** (Quote, Time), **Node.js** (Quote), **Go** (Time), **Java** (Quote). Full-featured: **system_plugins/homeclaw-browser** (Node.js — WebChat, browser automation, canvas, nodes) and a **companion plugin** (Python — same contract). See [Writing plugins and skills](writing-plugins-and-skills.md), [PluginsGuide.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/PluginsGuide.md), and [HowToWriteAPlugin.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/HowToWriteAPlugin.md) in the repo.
