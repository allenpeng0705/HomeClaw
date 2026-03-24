# How to Use HomeClaw

This is the practical guide after installation.

If you are brand new, start with `QuickStart.md` first.

---

## 1) Daily workflow

1. Start Core
2. Use Companion app and/or channels
3. Check health with doctor when needed

```bash
python -m main start
python -m main doctor
```

---

## 2) Core files you actually edit

- `config/core.yml` — server and core behavior
- `config/llm.yml` — model catalog and routing
- `config/user.yml` — users and friends
- `config/skills_and_plugins.yml` — tool/plugin/skill behavior
- `config/peers.yml` + `config/instance_identity.yml` — multi-instance federation

Tip: use Portal first; edit YAML only when needed.

---

## 3) LLM setup (simple)

### Local-only

- Put GGUF model(s) in your model folder
- Configure in `config/llm.yml` under `local_models`
- Set `main_llm` to `local_models/<id>`

### Cloud-only

- Configure `cloud_models` in `config/llm.yml`
- Set environment API key(s)
- Set `main_llm` to `cloud_models/<id>`

### Mix mode

In `config/llm.yml`:

- `main_llm_mode: mix`
- `main_llm_local: local_models/<id>`
- `main_llm_cloud: cloud_models/<id>`

---

## 4) Channels and Companion

### WebChat

```bash
python -m channels.run webchat
```

### Other channels

```bash
python -m channels.run telegram
python -m channels.run discord
python -m channels.run slack
```

Set `CORE_URL` in `channels/.env` for channel processes.

### Companion app

- Set Core URL (`http://127.0.0.1:9000` local)
- Set API key if auth is enabled
- Choose your user and chat

---

## 5) Skills and plugins

### Skills

- Built-in: `skills/`
- External/imported: `external_skills/`
- Install/remove via Portal or CLI

### Plugins

- Built-in Python plugins: `plugins/`
- External plugins (HTTP): register to Core

---

## 6) Better document output (VMPrint)

HomeClaw supports richer publishing output with VMPrint.

Use:

- `markdown_to_pdf` for straightforward PDF
- `vmprint_render` for advanced render:
  - `output_format: pdf` or `ast_json`
  - `vmprint_profile: academic | manuscript | screenplay | literature`
  - optional `vmprint_style`

---

## 7) Multi-instance federation

For remote friends across multiple HomeClaw instances:

- set instance identity: `config/instance_identity.yml`
- configure peers: `config/peers.yml`
- set federation flags in `config/core.yml`

Keep `peer_call_enabled: false` unless you intentionally want LLM-to-LLM cross-Core tool calls.

---

## 8) Troubleshooting checklist

1. `python -m main doctor`
2. Verify model entries and API keys
3. Verify channel `CORE_URL`
4. Check logs
5. In Portal Guide, run VMPrint smoke test if PDF output fails

---

## 9) Where to go next

- `README.md`
- `QuickStart.md`
- `InstallationGuide.md`
- `docs/getting-started.md`
- `docs/` (full docs site source)
