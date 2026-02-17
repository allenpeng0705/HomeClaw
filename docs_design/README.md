# Design and internal docs

This folder (**docs_design/**) holds **design documents and internal guides** (PluginsGuide, MemoryAndDatabase, ToolsDesign, Comparison, etc.). These are used for development and deep reference.

- The **documentation website** (GitHub Pages) is built from the **`docs/`** folder, not from this folder. See **`docs/README.md`** and **`mkdocs.yml`** at the repo root.
- Links from README, Design.md, Channel.md, and other repo files to “design docs” point to **docs_design/** (e.g. `docs_design/PluginsGuide.md`). **OutboundMarkdownAndUnknownRequest.md** — Outbound Markdown (for channels that can't display Markdown well) and optional unknown-request notification (notify owner via last-used channel so they can add identity to user.yml).
- **LineChannelAndChannelMediaAudit.md** — Line channel for HomeClaw (LINE Messaging API + webhook), channel audit for file/image/audio/video support, and WhatsApp evaluation (neonize vs OpenClaw Baileys; when to use Cloud API webhook).
