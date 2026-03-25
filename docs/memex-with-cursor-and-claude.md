# memex memory alongside the HomeClaw bridge

**[memex](https://github.com/iamtouchskyer/memex)** gives Cursor and Claude Code **persistent, markdown-based memory** (Zettelkasten-style cards in `~/.memex/cards/`). It does **not** replace the HomeClaw **Cursor / Claude Code bridge**; you keep both:

| Piece | Role |
|--------|------|
| **HomeClaw bridge** | Remote tasks from Companion/channels → open project, run agent, run shell on your dev machine. |
| **memex** | Local **memory** inside Cursor / Claude Code: recall & write cards across sessions. |

**Core** does not need memex for normal chat. Use the options below **on the dev machine** where you run the **Cursor / Claude Code bridge** if you want coding-agent memory.

---

## Prerequisites

- **Node.js 18+** on that machine (for bundled memex or global CLI).
- **Python** used to run HomeClaw (same interpreter you use for `python -m external_plugins.cursor_bridge.server`).
- Optional: **git** / **GitHub CLI** if you use `memex sync` ([upstream docs](https://github.com/iamtouchskyer/memex)).

---

## Recommended: HomeClaw bundled memex (same pack as the bridge)

Memex is **shipped as an optional npm bundle** next to the Cursor bridge so you do **not** need `npm install -g @touchskyer/memex`. Version is pinned in `external_plugins/cursor_bridge/bundled_memex/package.json` (currently `@touchskyer/memex` **0.1.22**).

### 1. Install the bundle once

From the **HomeClaw repository root**:

```bash
cd external_plugins/cursor_bridge/bundled_memex
npm ci
```

(`node_modules/` is gitignored; `package-lock.json` is tracked.)

**Installer:** If you use `install.sh` / `install.ps1` / `install.bat` with **Cursor** or **Claude Code** CLI install flags, **`npm ci` runs automatically** in `bundled_memex` (Step 2e). You can also set **`HOMECLAW_INSTALL_BUNDLED_MEMEX=1`** alone, or on Windows run **`install.bat memex`**. Set **`HOMECLAW_SKIP_BUNDLED_MEMEX=1`** to skip.

### 2. Cursor: MCP server → HomeClaw launcher

**Prefer a real Python 3** (Homebrew, pyenv, or your venv)—**not** Apple’s Xcode stub at `/Applications/Xcode.app/.../python3`, which often breaks tooling. On Apple Silicon Homebrew, that is usually `/opt/homebrew/bin/python3` (`which python3` in the same environment you use to run the bridge).

**Option A — run the launcher as a file (most reliable in Cursor)**  
Do **not** use `python -m external_plugins...` unless you also set `cwd` or `PYTHONPATH` (see Option B). Otherwise you get `ModuleNotFoundError: No module named 'external_plugins'`.

Python executes a **`.py` file** by path; no package import is needed. Use either:

- **Repo root** (shortest `args`): `homeclaw_memex_mcp.py` in the HomeClaw clone root (thin wrapper around `external_plugins/cursor_bridge/memex_mcp.py`).
- **Deep path:** `external_plugins/cursor_bridge/memex_mcp.py` directly.

```json
{
  "mcpServers": {
    "homeclaw-memex": {
      "command": "/opt/homebrew/bin/python3",
      "args": ["/absolute/path/to/HomeClaw/homeclaw_memex_mcp.py"]
    }
  }
}
```

**Conda example** (your `command` is the env’s `python`; `args` is still a single absolute path—no `-m`):

```json
{
  "mcpServers": {
    "homeclaw-memex": {
      "command": "/opt/anaconda3/envs/pytorch/bin/python",
      "args": ["/absolute/path/to/HomeClaw/memex_mcp.py"]
    }
  }
}
```

Replace `command` with your real interpreter (`which python3` or `conda which python`). Replace the path in `args` with your actual HomeClaw clone.

#### Why `python -m external_plugins...` often fails in Cursor

Cursor usually starts the MCP process **without** setting the working directory to your HomeClaw clone. Then `python -m external_plugins.cursor_bridge.memex_mcp` cannot import `external_plugins`, and the log shows:

```text
ModuleNotFoundError: No module named 'external_plugins'
```

That is **not** a conda bug: `-m` only works if the repo root is on `sys.path` (via **`cwd`**, **`PYTHONPATH`**, or running from that directory). **Option A** avoids the problem entirely by running **`homeclaw_memex_mcp.py`** (repo root) or **`memex_mcp.py`** (under `cursor_bridge`) as a plain script—no package import.

#### Example: clone at `/Users/shileipeng/Documents/mygithub/HomeClaw` + conda `pytorch`

If this matches your layout, you can paste (then reload MCP):

```json
{
  "mcpServers": {
    "homeclaw-memex": {
      "command": "/opt/anaconda3/envs/pytorch/bin/python",
      "args": ["/Users/shileipeng/Documents/mygithub/HomeClaw/memex_mcp.py"]
    }
  }
}
```

If you prefer **`-m`** with the same clone and env, add **`cwd`** or **`env.PYTHONPATH`**:

```json
{
  "mcpServers": {
    "homeclaw-memex": {
      "command": "/opt/anaconda3/envs/pytorch/bin/python",
      "args": ["-m", "external_plugins.cursor_bridge.memex_mcp"],
      "cwd": "/Users/shileipeng/Documents/mygithub/HomeClaw"
    }
  }
}
```

**Option B — `python -m` + repo root on `sys.path`**  
Either set **`cwd`** to the HomeClaw repo root, **or** set **`env.PYTHONPATH`** (works even if Cursor’s workspace is another folder):

```json
{
  "mcpServers": {
    "homeclaw-memex": {
      "command": "/opt/homebrew/bin/python3",
      "args": ["-m", "external_plugins.cursor_bridge.memex_mcp"],
      "cwd": "/absolute/path/to/HomeClaw"
    }
  }
}
```

```json
{
  "mcpServers": {
    "homeclaw-memex": {
      "command": "/opt/homebrew/bin/python3",
      "args": ["-m", "external_plugins.cursor_bridge.memex_mcp"],
      "env": {
        "PYTHONPATH": "/absolute/path/to/HomeClaw"
      }
    }
  }
}
```

**Option C — wrapper script** (no `cwd` needed; script `cd`s to the repo root, then `python -m`):

- macOS / Linux: `external_plugins/cursor_bridge/homeclaw_memex_mcp.sh` (make it executable: `chmod +x …`).
- Windows: `external_plugins/cursor_bridge/homeclaw_memex_mcp.cmd`

```json
{
  "mcpServers": {
    "homeclaw-memex": {
      "command": "/absolute/path/to/HomeClaw/external_plugins/cursor_bridge/homeclaw_memex_mcp.sh",
      "args": []
    }
  }
}
```

#### Troubleshooting (Cursor / MCP)

| Symptom | What to do |
|--------|------------|
| `ModuleNotFoundError: No module named 'external_plugins'` | You used `-m` without the repo on `sys.path` (Cursor often omits `cwd`). Use **Option A** (`homeclaw_memex_mcp.py` or `memex_mcp.py` by absolute path—**no `-m`**), or add **`cwd`** / **`env.PYTHONPATH`** (Option B). |
| Log shows Xcode’s `python3` | Point **`command`** at Homebrew/pyenv/venv **`python3`** with a full path, not bare `python3`. |
| Still fails after `npm ci` | Confirm `node` works in Terminal; if memex says Node missing, Cursor’s `PATH` may be thin—fix system PATH or use a wrapper that sources your shell profile. |

#### Windows (Cursor)

1. Install **Node.js 18+** and **Python 3** from [nodejs.org](https://nodejs.org/) and [python.org](https://www.python.org/) (or the Microsoft Store). In **Command Prompt** or **PowerShell**, check `node -v` and `py -3 --version` or `python --version`.
2. From the HomeClaw repo: `cd external_plugins\cursor_bridge\bundled_memex` then `npm ci` (same as on macOS/Linux).
3. **Option A — script path** (avoids `ModuleNotFoundError` if `cwd` is wrong):

```json
{
  "mcpServers": {
    "homeclaw-memex": {
      "command": "C:/path/to/python.exe",
      "args": ["C:/path/to/HomeClaw/external_plugins/cursor_bridge/memex_mcp.py"]
    }
  }
}
```

4. **`python -m` + `cwd` or `PYTHONPATH`** — same as macOS Option B above (`cwd` or `env.PYTHONPATH` pointing at the HomeClaw root).

5. **`.cmd` wrapper** — `homeclaw_memex_mcp.cmd` tries `py -3` first, then `python`. If Cursor does not start `.cmd` files directly, use **`cmd.exe`**:

```json
{
  "mcpServers": {
    "homeclaw-memex": {
      "command": "C:\\Windows\\System32\\cmd.exe",
      "args": [
        "/c",
        "C:\\path\\to\\HomeClaw\\external_plugins\\cursor_bridge\\homeclaw_memex_mcp.cmd"
      ]
    }
  }
}
```

6. If memex reports **Node not found**, Cursor may be using a minimal `PATH`. Add Node’s install directory to **system** environment variables, or install Node for “all users” so the GUI sees it.
7. **WSL:** If you run HomeClaw and the bridge **inside WSL**, use the Linux instructions (`python3`, `.sh`, or `cwd` to the Linux clone path), not the Windows `.cmd`.

After editing MCP config, restart Cursor or reload MCP. On Windows, cards live under `%USERPROFILE%\.memex\cards\` (same as upstream memex). On Unix, `~/.memex/cards/`.

### 3. HomeClaw Core + bundled memex (optional)

If Core runs on the **same machine** and should call memex via `mcp_call`, use the **absolute path** to `memex_mcp.py` as `args` (same as Cursor Option A), or `command` + `-m` with `cwd` / `PYTHONPATH` set to the repo root (see [Using MCP](mcp.md)).

---

## Alternative: global memex CLI

1. Install the CLI (from [memex README](https://github.com/iamtouchskyer/memex)):

   ```bash
   npm install -g @touchskyer/memex
   ```

2. In **Cursor** MCP config:

   ```json
   {
     "mcpServers": {
       "memex": {
         "command": "memex",
         "args": ["mcp"]
       }
     }
   }
   ```

   If `memex` is not on `PATH` for the GUI app, use the **full path** to the `memex` binary (`which memex` / `where memex`).

3. Restart Cursor or reload MCP.

When HomeClaw’s bridge **opens Cursor** or **runs the Cursor agent**, that Cursor instance can use memex the same way—bundled launcher vs global CLI is only how the MCP process is started.

---

## Claude Code: memex plugin

From [memex’s install table](https://github.com/iamtouchskyer/memex):

```text
/plugin marketplace add iamtouchskyer/memex
/plugin install memex@memex
```

The plugin handles hooks (e.g. recall on session start) and skills. **Claude Code** and **Cursor** can both use the **same** `~/.memex/cards/` directory if both are on the same machine.

If the plugin marketplace fails (e.g. SSH to GitHub), use **MCP** instead (below).

**Marketplace clone uses SSH by default** (`git@github.com:…`). If you see `Permission denied (publickey)`:

- Configure [GitHub SSH keys](https://docs.github.com/en/authentication/connecting-to-github-with-ssh), then retry `/plugin marketplace add iamtouchskyer/memex`, **or**
- Try an HTTPS URL if your Claude Code build accepts it:  
  `/plugin marketplace add https://github.com/iamtouchskyer/memex`  
  (or `https://github.com/iamtouchskyer/memex.git`).

---

## Claude Code: memex via MCP

Claude Code can attach **stdio** MCP servers with the CLI. Official overview: [Connect Claude Code to tools via MCP](https://docs.anthropic.com/en/docs/claude-code/mcp).

**Important:** Put **`--transport stdio`**, **`--env`**, **`--scope`**, etc. **before** the server name. A **`--`** separates the server name from the command that starts the MCP process.

### Global `memex` on PATH

After `npm install -g @touchskyer/memex` (and `npm ci` *not* required for this path):

```bash
claude mcp add --transport stdio memex -- memex mcp
```

If `memex` is not on the PATH Claude Code uses, use the full path to the `memex` binary instead of `memex`.

### HomeClaw bundled memex (same as Cursor)

Use the **repo-root launcher** so you do not need `cwd` / `PYTHONPATH` for `external_plugins` (same idea as Cursor **Option A** in this doc). Replace paths with yours:

```bash
claude mcp add --transport stdio homeclaw-memex -- /opt/homebrew/bin/python3 /absolute/path/to/HomeClaw/homeclaw_memex_mcp.py
```
###For Winodws
```bash
claude mcp add --transport stdio homeclaw-memex -- C:/Users/PS/anaconda3/envs/pytorch/python.exe D:\\mygithub\\HomeClaw\\external_plugins\\cursor_bridge\\memex_mcp.py
```

**Conda example:**

```bash
claude mcp add --transport stdio homeclaw-memex -- /opt/anaconda3/envs/pytorch/bin/python /absolute/path/to/HomeClaw/homeclaw_memex_mcp.py
```

You still need **`npm ci`** once under `external_plugins/cursor_bridge/bundled_memex` (Node required for the bundled CLI).

### Optional: pass environment variables

Use repeated `--env KEY=value` **before** the server name (see `claude mcp add --help`).

### Check and remove

```bash
claude mcp list
claude mcp get homeclaw-memex
# Inside Claude Code:
/mcp
```

```bash
claude mcp remove homeclaw-memex
```

### Notes

- Cards still live under **`~/.memex/cards/`** (same store as Cursor and the memex plugin).
- **MCP** exposes memex’s **tools** in Claude Code; it does **not** install the memex **plugin** hooks/skills from the marketplace. Use **`/plugin install …`** when the marketplace works if you want those extras.
- Wider MCP options (HTTP servers, headers, scopes): [Connect Claude Code to tools via MCP](https://docs.anthropic.com/en/docs/claude-code/mcp).

### Example: one copy-paste command

If HomeClaw is cloned at **`/Users/shilepeng/Documents/mygithub/HomeClaw`** and you use conda env **`pytorch`** (same layout as a typical Anaconda install):

```bash
claude mcp add --transport stdio homeclaw-memex -- /opt/anaconda3/envs/pytorch/bin/python /Users/shilepeng/Documents/mygithub/HomeClaw/homeclaw_memex_mcp.py
```

Change the Python path and the path to **`homeclaw_memex_mcp.py`** to match your machine. You still need **`npm ci`** once in `external_plugins/cursor_bridge/bundled_memex` inside that clone.

---

## Shared store and sync

- All clients share **`~/.memex/cards/`**.
- Optional: **`memex sync`** with a private git repo so cards follow you across machines ([memex README — Cross-platform sharing](https://github.com/iamtouchskyer/memex)).
- Optional: **`memex serve`** for a local timeline UI (default port **3939** per upstream docs).

---

## Integrating memex with HomeClaw: what “communicate” can mean

**memex** is **not** a message bus between Cursor and HomeClaw. It is **local markdown cards** that any client can read/write if it runs the memex MCP (or plugin) against `~/.memex/cards/`.

| Goal | Mechanism today | Notes |
|------|-----------------|--------|
| **HomeClaw → Cursor** (tasks, agent, shell) | **Cursor bridge** (`external_plugins.cursor_bridge`) | This is the real “Companion talks to your dev machine” path. |
| **Cursor / Claude Code ↔ same memory** | **memex** (MCP + plugin) on the **same machine** | Same folder; no HomeClaw in the loop. |
| **HomeClaw LLM ↔ memex cards** | Optional **`tools.mcp.servers` → memex** (see below) | Only practical when **Core runs on the same host** (or a volume that contains the same `cards/` tree) as memex. |
| **“When the agent finishes, tell HomeClaw”** | Not built into memex | Would need **custom** glue: e.g. a script/hook that calls Core’s HTTP API, a small skill, or bridge extension—not memex itself. |

So you **can** “integrate” memex with HomeClaw in the sense of **one shared card store** used by Companion (via Core + `mcp_call`) **and** by Cursor/Claude—**if** filesystem (or synced git copy of cards) is shared. That does **not** replace the bridge for **delegating work** to Cursor; it **adds** optional recall/write for the **HomeClaw** side of the house.

If Core runs **only on a server** and your IDE is **only on your laptop**, Core will not see `~/.memex/cards/` on the laptop unless you **sync** that directory (e.g. git, rsync, or a mount) to somewhere Core can read, or you add an app-level sync/API (future work).

---

## Optional: HomeClaw Core + memex (advanced)

If **Core runs on the same machine** as `memex` and you want the **HomeClaw LLM** to read/write cards via **`mcp_call`**, add under **`tools.mcp.servers`** in `config/skills_and_plugins.yml`:

```yaml
memex:
  transport: stdio
  command: /absolute/path/to/HomeClaw/external_plugins/cursor_bridge/homeclaw_memex_mcp.sh
  args: []
```

On Windows, use `homeclaw_memex_mcp.cmd`, or `command` + absolute path to `memex_mcp.py` in `args` (same as Cursor Option A). If your MCP client supports `cwd` or `env`, you may use `python -m external_plugins.cursor_bridge.memex_mcp` with repo root on `sys.path`. Otherwise use a global `memex` binary as in the alternative section above.

See [Using MCP](mcp.md). Skip this if you only want **Cursor/Claude** to use memex—it keeps concerns separated.

---

## Summary

- **Packaging (with bridge):** `npm ci` in `external_plugins/cursor_bridge/bundled_memex`, then Cursor MCP → **best:** full path to Python + absolute path to **`homeclaw_memex_mcp.py`** (repo root) or `external_plugins/cursor_bridge/memex_mcp.py` in `args`; **or** `-m` with `cwd` / `PYTHONPATH` = HomeClaw root. Avoid bare `python3` (often Xcode on macOS). No global memex required.
- **Alternative:** `npm install -g @touchskyer/memex` and MCP `memex` / `mcp` as upstream documents.
- **Claude Code:** memex **plugin** from upstream (`/plugin install memex@memex`), or **MCP** via `claude mcp add --transport stdio …` (see **Claude Code: memex via MCP** above); bundled npm tree feeds the same launcher as Cursor.
- **No duplicate memory system:** memex is for **coding-agent** notes; HomeClaw’s own memory (RAG, agent memory, etc.) stays for **assistant** chat.

---

## Related: making outputs “magazine-style” (VMPrint PDF)

Separately from memex, HomeClaw can generate **beautiful, magazine-style PDFs** for long outputs (daily brief, weather, stock reports, etc.) using **VMPrint** ([`cosmiciron/vmprint`](https://github.com/cosmiciron/vmprint)).

- Use the skill **`magazine-render-1.0.0`** to render **Markdown → PDF** (or **JSON → template → PDF**) and return an `output/*.pdf` link.
- See [`docs/examples.md`](examples.md) “Example 4b: Magazine-style PDF for any content (skill)” for copy-paste usage.

This is useful when you want the final response to be more readable than a long chat message.
