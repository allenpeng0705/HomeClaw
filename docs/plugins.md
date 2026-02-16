# Plugins

*How to extend HomeClaw with plugins. Replace with curated content from docs_design/PluginsGuide.md.*

---

Plugins add focused capabilities: weather, news, email, custom APIs. One plugin = one feature.

- **Built-in (Python)** — In `plugins/` with `plugin.yaml`, `config.yml`, `plugin.py`. Core discovers them at startup.
- **External (any language)** — Run as an HTTP server; register with Core via `POST /api/plugins/register`.

See [PluginsGuide.md](../docs_design/PluginsGuide.md) and [HowToWriteAPlugin.md](../docs_design/HowToWriteAPlugin.md) in the repo.
