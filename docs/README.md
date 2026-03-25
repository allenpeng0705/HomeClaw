# HomeClaw Docs

**Website:** [https://www.homeclaw.cn](https://www.homeclaw.cn)  
**Docs site:** [https://allenpeng0705.github.io/HomeClaw/](https://allenpeng0705.github.io/HomeClaw/)

This folder is the source of the docs site (MkDocs).

## Start Here

1. [getting-started.md](getting-started.md)
2. [install.md](install.md)
3. [run.md](run.md)
4. [portal.md](portal.md)
5. [models.md](models.md)

## Core Topics

- Stock monitor skill (watchlist, alerts, Chinese symbols, cron notifications): [../documentation/README.md](../documentation/README.md)
- memex memory with Cursor / Claude Code (alongside the bridge): [memex-with-cursor-and-claude.md](memex-with-cursor-and-claude.md)
- Channels: [channels.md](channels.md)
- Companion app: [companion-app.md](companion-app.md)
- Plugins and skills: [plugins.md](plugins.md), [writing-plugins-and-skills.md](writing-plugins-and-skills.md)
- Multi-instance/federation: [multi-instance-peers.md](multi-instance-peers.md), [federated-companion-messaging.md](federated-companion-messaging.md)
- Remote access and auth: [remote-access.md](remote-access.md)

## Minimal Usage Examples

### Run Core

```bash
python -m main start
```

### Run Portal

```bash
python -m main portal
```

### Run WebChat

```bash
python -m channels.run webchat
```

### Generate better PDF output (VMPrint)

Use `markdown_to_pdf` or `vmprint_render` and set:

- `vmprint_profile`: `academic | manuscript | screenplay | literature`
- optional `vmprint_style`

## Build docs locally

From repo root:

```bash
pip install mkdocs-material -e .
mkdocs serve
```

Open `http://127.0.0.1:8000`.

---

Note: deep design documents are in `docs_design/` (not part of MkDocs navigation by default).
