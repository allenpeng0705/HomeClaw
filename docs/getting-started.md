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

3. **Run Core** — `python -m core.core` or `python -m main start`

4. **Run a channel** — e.g. `python -m channels.run webchat` and open http://localhost:8014

For full steps, see the main [README](https://github.com/allenpeng0705/HomeClaw/blob/main/README.md) and [HOW_TO_USE.md](https://github.com/allenpeng0705/HomeClaw/blob/main/HOW_TO_USE.md) in the repo.
