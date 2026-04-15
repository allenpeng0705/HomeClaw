# Magazine AST chrome templates (HomeClaw)

## Upstream VMPrint

Canonical **AST `1.1` shape**, built-in font families, and the **engine API** are described in the upstream **[VMPrint QUICKSTART](https://github.com/cosmiciron/vmprint/blob/main/QUICKSTART.md)**. For the **`vmprint` CLI** (global install, flags, layout stream options), see **[cli/QUICKSTART.md](https://github.com/cosmiciron/vmprint/blob/main/cli/QUICKSTART.md)**.

HomeClaw’s `render_magazine.py` shells the **monorepo** build: `node <vmprint-root>/cli/dist/index.js` (after `npm run build` in a full [cosmiciron/vmprint](https://github.com/cosmiciron/vmprint) clone). That matches “run from source” in the CLI quickstart; use `HOMECLAW_VMPRINT_ROOT`, `VMPRINT_ROOT`, or `HOMECLAW_VMPRINT_CLI` / `VMPRINT_CLI` when the clone is not under `tools/vmprint`.

**Install VMPrint manually (clone, npm, env, troubleshooting):** [Manual installation for HomeClaw](../../../docs/vmprint-ui-runtime.md#manual-installation-for-homeclaw).

## What lives here

- **`daily_brief_magazine_chrome_v1.json`** — **Chrome-only** fragment: `layout`, `styles`, `header`, `footer`, plus `meta.homeclaw_template` describing merge mode `chrome_only`.
- **`demo_rss_input.json`** — small RSS-shaped payload for the preview command below.

At render time, `render_magazine.py` still builds **story `elements`** from RSS/Tavily-shaped JSON (`_daily_brief_magazine_ast` / newspaper path). The chrome file **overlays** typography and page frame so you can iterate on the look without duplicating item logic.

## How to use

### Generate one preview (browser HTML)

Requires a **built** VMPrint workspace (`cli/dist/index.js` after `npm run build`; default `tools/vmprint` or override via env — see **Troubleshooting** below). From repo root:

```bash
python3 skills/magazine-render-1.0.0/scripts/render_magazine.py render-daily-brief-ast \
  --document-layout magazine \
  --chrome-template skills/magazine-render-1.0.0/ast_templates/daily_brief_magazine_chrome_v1.json \
  --input skills/magazine-render-1.0.0/ast_templates/demo_rss_input.json \
  --title "CHROME DEMO" \
  --theme dispatch \
  --output_format browser_preview_html \
  --out magazine_chrome_demo.preview.html
```

On success the script prints JSON with `output_rel_path` like `output/magazine_chrome_demo.preview.html`.

- **Local file URL:** open `file://` + absolute path to that file, e.g. `file:///Users/you/HomeClaw/output/magazine_chrome_demo.preview.html` (path is under `output/` next to copied VMPrint assets).
- **One HTTP link (Companion / channels):** run the same flow through Core **`run_skill`** on `magazine-render-1.0.0` with the same args; when `core_public_url` (or your files route) is set, the tool result includes a **`/files/out?...`** view link you can paste into a browser.

### Layout JSON only (no VMPrint canvas)

```bash
python3 skills/magazine-render-1.0.0/scripts/render_magazine.py render-daily-brief-ast \
  --document-layout magazine \
  --chrome-template skills/magazine-render-1.0.0/ast_templates/daily_brief_magazine_chrome_v1.json \
  --json '{"as_of":"2026-04-15","items":[...]}' \
  --output_format layout_json \
  --out rss_mag.layout.json
```

(Adjust paths from repo root; under `run_skill`, paths are relative to the sandbox/output rules Core uses.)

## Troubleshooting: `VMPrint CLI missing … cli/dist/index.js`

HomeClaw expects a **built** VMPrint workspace at **`tools/vmprint`** (this path is **gitignored** — you clone upstream yourself; it is not shipped inside the HomeClaw git tree).

### 0. VMPrint lives outside `tools/vmprint` (optional)

If your clone is elsewhere (but **already built**), point magazine-render at it:

```bash
export HOMECLAW_VMPRINT_ROOT=/path/to/vmprint
# or: export VMPRINT_ROOT=/path/to/vmprint
```

That directory must contain **`cli/dist/index.js`** (same layout as upstream [cosmiciron/vmprint](https://github.com/cosmiciron/vmprint)).

Alternatively, set the CLI file directly:

```bash
export HOMECLAW_VMPRINT_CLI=/path/to/vmprint/cli/dist/index.js
# or: export VMPRINT_CLI=... (same path)
```

A global **`npm install -g @vmprint/cli`** (see [vmprint CLI quickstart](https://github.com/cosmiciron/vmprint/blob/main/cli/QUICKSTART.md)) is fine for ad‑hoc `vmprint --input … --output …` on your machine; HomeClaw’s magazine-render still uses the **workspace** `cli/dist/index.js` path above so `cwd` and bundled assets stay consistent with the repo layout.

### 1. Build the CLI

```bash
cd tools/vmprint
npm install
npm run build
```

Check:

```bash
test -f tools/vmprint/cli/dist/index.js && echo OK
node tools/vmprint/cli/dist/index.js --help
```

### 2. First-time install from repo root

The main installer also clones and builds VMPrint (see `install.sh`, “Step 4b”):

```bash
./install.sh
```

(Ensure **Node.js** and **npm** are on your `PATH`.)

### 3. `createPrintEngineRuntime` / esbuild “No matching export” during `npm run build`

That means **`cli` and `engine` are out of sync** (old partial tree or mixed copies). Because `tools/vmprint` is gitignored, replace it with a **fresh** clone of [cosmiciron/vmprint](https://github.com/cosmiciron/vmprint), then build again:

```bash
cd /path/to/HomeClaw
rm -rf tools/vmprint
git clone --depth 1 https://github.com/cosmiciron/vmprint.git tools/vmprint
cd tools/vmprint && npm install && npm run build
```

### 4. Broken clone (`tools/vmprint` only contains `.git` or “No commits yet”)

Remove the folder and run the clone + build commands in section 3 again (stable network required).

## Upstream VMPrint fixtures (reference)

After `install.sh` / clone, VMPrint ships **regression fixtures** for **scripted documents** (YAML methods + JSON body):

**`tools/vmprint/engine/tests/fixtures/scripting/`**

Examples:

- `00-hello-world.json` — minimal `onLoad` / `documentVersion` `1.1`
- `02-ready-summary.json` — `onReady()` messaging and settled layout facts

Those files use the **combined** format:

```text
---
methods:
  onReady(): |
    ...
---
{ "documentVersion": "1.1", "layout": { ... }, ... }
```

That is **not** the same as HomeClaw’s **chrome-only JSON** (no YAML block). Use upstream fixtures when you:

- Prototype **VMPrint scripting** (`onReady`, `sendMessage`, zone live edits).
- Copy **layout / element patterns** that match the engine’s expectations.

HomeClaw’s **magazine-render** path for RSS/news uses **pure JSON AST** passed to the CLI; scripting is optional elsewhere (e.g. `web_search` colophon in `render_magazine.py`). To combine **chrome merge** with **scripting**, you would extend the pipeline to emit the YAML+JSON file format `_write_ast_input_file` already supports — not covered by `chrome_only` v1.

## Regenerating `daily_brief_magazine_chrome_v1.json`

From repo root (requires `skills/magazine-render-1.0.0/scripts` on `PYTHONPATH`):

```python
import copy, json
from pathlib import Path
import sys
sys.path.insert(0, "skills/magazine-render-1.0.0/scripts")
from render_magazine import _daily_brief_magazine_ast

mock = {"as_of": "2026-04-15", "items": [{"title": "…", "feed": "…", "summary": "…", "link": "https://…"}]}
ast = _daily_brief_magazine_ast(mock, title="DAILY BRIEF", theme="dispatch")
chrome = {
    "layout": copy.deepcopy(ast["layout"]),
    "styles": copy.deepcopy(ast["styles"]),
    "header": copy.deepcopy(ast["header"]),
    "footer": copy.deepcopy(ast["footer"]),
    "meta": {"homeclaw_template": {"kind": "daily_brief_magazine_chrome", "version": 1, "merge_mode": "chrome_only"}},
}
Path("skills/magazine-render-1.0.0/ast_templates/daily_brief_magazine_chrome_v1.json").write_text(
    json.dumps(chrome, ensure_ascii=False, indent=2), encoding="utf-8"
)
```
