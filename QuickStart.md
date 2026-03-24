# HomeClaw Quick Start

This guide is the shortest path from zero to first chat.

## 1) Install

| Platform | Command |
|---|---|
| macOS / Linux | `bash install.sh` |
| Windows | `install.bat` (or `.\install.ps1`) |

What installer does:

- checks Python/Node
- installs Python deps
- installs helper CLIs (optional)
- installs VMPrint support for better PDF output
- opens Portal at `http://127.0.0.1:18472`

## 2) Configure in Portal

In Portal:

1. Create admin account
2. Open **Manage settings -> LLM**
3. Choose your main model
4. Add user(s)
5. Start Core

## 3) Run Core

```bash
python -m main start
```

Core default address: `http://127.0.0.1:9000`

Health check:

```bash
python -m main doctor
```

## 4) Chat

### Companion app

- Open app
- Set Core URL to `http://127.0.0.1:9000`
- If auth enabled, add API key
- Login/use your configured user

### WebChat channel

```bash
python -m channels.run webchat
```

## 5) Practical examples

### Example: use mix mode

In `config/llm.yml`:

- `main_llm_mode: mix`
- `main_llm_local: local_models/<id>`
- `main_llm_cloud: cloud_models/<id>`

### Example: generate a better PDF

Use tool `vmprint_render`:

- `output_format: pdf`
- `vmprint_profile: academic | manuscript | screenplay | literature`
- optional `vmprint_style`

### Example: export VMPrint AST JSON

Use tool `vmprint_render`:

- `output_format: ast_json`
- `path: output/<name>.ast.json`

---

More docs:

- `README.md`
- `InstallationGuide.md`
- `HOW_TO_USE.md`
