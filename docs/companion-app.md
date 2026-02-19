# Companion app (Flutter)

The **HomeClaw Companion** app is a **Flutter-based** client for **Mac, Windows, iPhone, and Android**. It makes HomeClaw much easier to use from any device.

---

## What it does

- **Chat** — Send messages, attach images and files; voice input and TTS (speak replies).
- **Manage Core** — Edit **core.yml** and **user.yml** from the app: server, LLM, memory, session, completion, profile, skills, tools, auth, and users. No need to SSH or edit config files by hand.
- **One app, all platforms** — Same codebase for desktop and mobile; install from the store or build from source.

---

## Where to get it

- **Source:** `clients/homeclaw_companion/` in the repo.
- **Build:** Use Flutter; see `clients/homeclaw_companion/README.md` for build instructions.
- **Connect:** Set the Core URL and optional API key in the app (e.g. in Settings or on first launch). The app talks to your Core over HTTP (e.g. `http://127.0.0.1:9000` or your server URL).

You can use the companion app **instead of** or **together with** WebChat, CLI, Telegram, and other channels—all talk to the same Core and memory.
