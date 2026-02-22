# Getting started

*Quick start for the doc site. You can replace with curated steps from README and HOW_TO_USE.md.*

---

1. **Clone and install**

   ```bash
   git clone https://github.com/allenpeng0705/HomeClaw.git
   cd HomeClaw
   pip install -r requirements.txt
   ```

2. **Configure** — Edit `config/core.yml` (LLM, memory) and `config/user.yml` (who can talk to the assistant).

   - **Local models:** Copy llama.cpp's **binary distribution** into `llama.cpp-master/<platform>/` for your device (e.g. `mac/`, `win_cuda/`, `linux_cpu/` — see `llama.cpp-master/README.md` in the repo). Used for main and embedding local models.
   - **Cloud models:** Set API keys in the environment (e.g. `export GEMINI_API_KEY=...`).

3. **Run Core** — `python -m main start` (recommended: starts Core and built-in CLI) or `python core/core.py` (Core only). Both run the same Core server.

   **Verify core is up:** In another terminal, run `curl -s http://127.0.0.1:9000/ready` — you should get a 200 response (and a short body). Core listens on the port set in `config/core.yml` (default 9000).

4. **Run a channel** — e.g. `python -m channels.run webchat` and open http://localhost:8014, or use the **Companion app** (Flutter: Mac, Windows, iPhone, Android) from `clients/homeclaw_companion/` to chat and **Manage Core** (edit config from the app).

For full steps, see the main [README](https://github.com/allenpeng0705/HomeClaw/blob/main/README.md) and [HOW_TO_USE.md](https://github.com/allenpeng0705/HomeClaw/blob/main/HOW_TO_USE.md) in the repo.
