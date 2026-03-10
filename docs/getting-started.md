# Getting started

Quick path from install to chatting with HomeClaw via the **Companion app** and/or **channels** (WebChat, Telegram, etc.). They all talk to the same **Core**—run Core once, then use the app and any channel together.

---

1. **Install (first step)**

   **Recommended:** Run the install script. Clone the repo (`git clone https://github.com/allenpeng0705/HomeClaw.git`, `cd HomeClaw`), then:

   - **Mac/Linux:** Run `chmod +x install.sh` (one-time) then `./install.sh`, or run `bash install.sh` (no chmod needed). If `./install.sh` gives "Permission denied", use one of these.
   - **Windows:** Use **PowerShell** (not Command Prompt). Run `.\install.ps1`. If you get an execution policy error, run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` once, or use `powershell -ExecutionPolicy Bypass -File .\install.ps1`. See [Install](install.md) for details.

   The script checks Python, installs dependencies, and **opens the Portal** at **http://127.0.0.1:18472** when done.

   **Manual alternative:** `pip install -r requirements.txt` after cloning (see [Install](install.md)).

2. **Configure** — Edit `config/core.yml` (LLM, memory) and `config/user.yml` (who can talk to the assistant). Or use the **Portal**: run `python -m main portal` and open **http://127.0.0.1:18472** in your browser to manage settings and users.

   - **Local models:** Copy llama.cpp's **binary distribution** into `llama.cpp-master/<platform>/` for your device (see `llama.cpp-master/README.md` in the repo).
   - **Cloud models:** Set API keys in the environment (e.g. `export GEMINI_API_KEY=...`).

3. **Run Core** — `python -m main start` (starts Core and built-in CLI; web UI opens). Core is the single backend for the Companion app and all channels.

   **Verify:** `curl -s http://127.0.0.1:9000/ready` should return 200. Or run `python -m main doctor` to check config and LLM.

4. **Use the Companion app and/or channels**

   - **Companion app** — Install from `clients/HomeClawApp/`. In Settings set **Core URL** to `http://127.0.0.1:9000` (same machine) or your remote URL (Tailscale, Cloudflare Tunnel, etc.). Add your user in `config/user.yml` or via Portal. Open **Chat** to talk to HomeClaw; use **Settings** for **Skills** (install/remove via ClawHub) and **Manage Core** (edit config).
   - **Channels** — With Core running, run e.g. `python -m channels.run webchat` and open http://localhost:8014. Set `CORE_URL` in `channels/.env`. Same Core, same memory as the Companion app.

   **Companion and channels together:** Run Core once. The app and every channel connect to that same Core; you can use both at the same time.

For full steps, see [QuickStart.md](https://github.com/allenpeng0705/HomeClaw/blob/main/QuickStart.md), the main [README](https://github.com/allenpeng0705/HomeClaw/blob/main/README.md), and [HOW_TO_USE.md](https://github.com/allenpeng0705/HomeClaw/blob/main/HOW_TO_USE.md) in the repo.
