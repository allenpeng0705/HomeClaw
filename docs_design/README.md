# Design and internal docs

This folder (**docs_design/**) holds **design documents and internal guides** (PluginsGuide, MemoryAndDatabase, ToolsDesign, Comparison, etc.). These are used for development and deep reference.

- **UserFriendsModelFullDesign.md** — **Master design** for the user/friends model: user.yml (friends list, identity), Companion login and friends-only UI, data scoping per (user_id, friend_id), memory paths, profile, sandbox auto-creation, friend identity.md, push (from_friend), channels (HomeClaw), and the 14-step implementation plan. Implement changes step by step from this doc.

- **SocialNetworkDesign.md** — **Summary** of the social network for one HomeClaw (users, friends AI + user-type, channels, Companion, user-to-user, push, security) and **future extension** to multi-HomeClaw (instances connect; users across instances communicate). Summarize first, then implement.

- **FederatedCompanionUserMessaging.md** — **Plan** for Companion **user-to-user chat across HomeClaw instances**: non-breaking friend schema (`peer_instance_id`), `federation_enabled`, dedicated **`POST /api/federation/user-message`**, reuse **`peers.yml`** trust, phased P0–P5 (request/accept, Companion UI, optional E2E).

- **MultiInstanceIdentityRosterAndPairing.md** — Multi-HomeClaw coordination: **`instance_identity.yml`**, **`peers.yml`**, **`peer_call`**, pairing API + **`python -m main peer`** (invite-create / invite-accept / **import** / list), consume rate limit. Connection uses **`POST /inbound`**.

- The **documentation website** (GitHub Pages) is built from the **`docs/`** folder, not from this folder. See **`docs/README.md`** and **`mkdocs.yml`** at the repo root.
- Links from README, Design.md, Channel.md, and other repo files to “design docs” point to **docs_design/** (e.g. `docs_design/PluginsGuide.md`). **OutboundMarkdownAndUnknownRequest.md** — Outbound Markdown (for channels that can't display Markdown well) and optional unknown-request notification (notify owner via last-used channel so they can add identity to user.yml).
- **LineChannelAndChannelMediaAudit.md** — Line channel for HomeClaw (LINE Messaging API + webhook), channel audit for file/image/audio/video support, and WhatsApp evaluation (neonize vs OpenClaw Baileys; when to use Cloud API webhook).
