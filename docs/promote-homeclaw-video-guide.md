# How to Make Demo and Promo Videos for HomeClaw

Video is one of the best ways to show what HomeClaw does. This guide suggests **video types**, **what to show**, **tools**, and **short script ideas** so you can plan and produce demos and promos.

---

## 1. Video types that work

| Type | Length | Goal | Best for |
|------|--------|------|----------|
| **Hero / overview** | 1–2 min | First impression: what is HomeClaw, why care | Homepage, social teaser |
| **Feature highlight** | 30–90 sec each | One strength per clip: Companion, mix mode, plugins, multi-agent | YouTube, X/Twitter, LinkedIn |
| **Live demo** | 2–5 min | Real usage: chat, voice, edit config, ask for weather | Devs, evaluators |
| **Tutorial / how-to** | 3–8 min | “How to enable mix mode,” “How to add a plugin” | Docs, search, SEO |
| **Story / pitch** | 1–2 min | Narrative: Python stack, save cost, extend, multi-agent | Website, investors, partners |

Start with **one hero** (1–2 min) and **2–3 feature clips** (30–60 sec each). Add tutorials and longer demos as you go.

---

## 2. What to show (by strength)

### Companion app

- **Screen recording:** Companion on Mac or phone.
- **Show:** Open app → type or speak → get reply (with voice if TTS on). Then open **Manage Core** → tap a section (e.g. LLM or server) → show core.yml / user.yml in the app. Say: “Same app on phone and laptop; edit config without SSH.”
- **Hook:** “Chat and manage your AI from one app—Mac, Windows, iPhone, Android.”

### Mix mode (save cost)

- **Screen recording:** Core running with mix mode on; optional: usage report or log.
- **Show:** Send a simple message (e.g. “Hello”) → reply has `[Local · heuristic]` or similar. Send a harder query (e.g. “Search for latest news on…”) → reply has `[Cloud · semantic]` or similar. Optionally open usage report in chat or API: “How much went to cloud?” Show the numbers.
- **Hook:** “Local when it’s easy, cloud when it’s hard—you control cost per request.”

### Plugins (built-in + external)

- **Built-in:** Show a plugin in `plugins/` (e.g. Weather): folder, `plugin.yaml`, short `plugin.py`. In chat: “What’s the weather in Tokyo?” → model calls plugin, shows result.
- **External:** If you have an external plugin (e.g. Node.js): show it as HTTP server, register with Core (API or config), then same chat flow. Say: “Python plugins in the repo; external plugins in any language—register and go.”
- **Hook:** “One plugin, one capability. Python inside, any language outside.”

### Multi-agent

- **Show:** Two terminal windows or two Companion/WebChat tabs: one to port 9000, one to 9001. Same Core codebase, different ports (and optionally different config). Send different questions to each; show different “agents” (e.g. different system prompts or skills).
- **Hook:** “One instance = one agent. More instances = more agents. No orchestrator.”

### Python tech stack (for devs)

- **Show:** Project layout: `core/`, `plugins/`, `config/`. Open `core/core.py` briefly (FastAPI, uvicorn). Open a built-in plugin `plugin.py`. Run Core from terminal: `python -m core.core` or your run command. Say: “Core is Python—FastAPI, uvicorn. Plugins are Python. The AI world runs on Python; so does HomeClaw.”

---

## 3. Tools and workflow

- **Screen recording:** OBS (free), QuickTime (Mac), or built-in (e.g. Windows Game Bar, iOS Screen Record). Record at 1080p; 30 fps is enough for demos.
- **Voiceover:** Record in a quiet room; or use a script and record narration in OBS or a DAW (e.g. Audacity). Keep tone clear and calm.
- **Editing:** DaVinci Resolve (free), CapCut, or iMovie. Cut long pauses; add short titles or captions for key points (e.g. “Mix mode: local vs cloud”).
- **Thumbnails and captions:** One clear frame or a simple title card; captions (especially for social) increase reach.
- **Export:** 1080p MP4; for social, also export 1:1 or 9:16 if you target Stories/Reels.

**Workflow:** Script (3–5 bullets) → record screen + voice (or voice later) → cut to length → add one title card at start (and optionally at end with repo/docs link) → export.

---

## 4. Short script ideas

### Hero (1–2 min)

1. “HomeClaw is an AI assistant that runs on your machine—your data, your control.”
2. “Talk to it from the Companion app on your phone or laptop: chat, voice, and edit config without SSH.”
3. “Use local models, cloud models, or both. Mix mode routes each request so you save cost.”
4. “Extend it with Python plugins or external plugins in any language. Run multiple agents by running multiple instances.”
5. “Python at the core, one app for all devices. Your home, your AI—try it.”

### Companion (30–60 sec)

1. “This is the HomeClaw Companion—one app for Mac, Windows, iPhone, and Android.”
2. [Show chat + voice.] “Chat and voice, same Core and memory everywhere.”
3. [Show Manage Core → config.] “Manage Core: edit core.yml and user.yml from the app. No SSH.”
4. “One app, all devices. Link in the description.”

### Mix mode (30–60 sec)

1. “Mix mode: one request, one choice—local or cloud.”
2. [Show simple message → Local.] “Simple or private? Local.”
3. [Show complex message → Cloud.] “Search or complex? Cloud.”
4. [Show usage report if possible.] “See how much went to cloud; tune rules. You control cost.”

### Plugins (30–60 sec)

1. “Plugins add one capability at a time. Built-in ones are Python, in the repo.”
2. [Show plugin folder + chat calling it.] “Weather, news, your own plugin—the LLM routes to them.”
3. “External plugins: any language, HTTP server, register with Core. Python at the core, any language at the edge.”

---

## 5. Where to publish

- **YouTube:** Hero + feature playlist; tutorials (longer) for SEO. Put repo and docs in description and end card.
- **X / Twitter, LinkedIn:** 30–60 sec feature clips; same hero cut to 60–90 sec. Captions recommended.
- **Website / docs:** Embed hero on homepage; link “See how it works” to feature clips or live demo.
- **GitHub:** Add “Demo” section to README with links to hero and 1–2 key features.

---

## 6. Checklist before publishing

- [ ] Repo URL and docs URL in description and/or end card.
- [ ] Clear audio; no long silent stretches.
- [ ] One main message per clip.
- [ ] Thumbnail with “HomeClaw” and one short hook (e.g. “Python-native AI assistant” or “Mix mode: save cost”).
- [ ] Captions or on-screen text for key terms (Companion, mix mode, plugins, multi-agent).

Start with a **hero** and **Companion + mix mode** clips; they show “what it is” and “why it’s useful” quickly. Add plugin and multi-agent clips next, then tutorials as you get feedback.
