# Response output policy (plaintext, Markdown, VMPrint)

HomeClaw can surface answers in three main shapes. This document is the **product policy** for when to use each. Core **injects a short version** of this into the system prompt when `tools.response_output_policy_in_prompt` is true (default) in `config/skills_and_plugins.yml`.

## 1. Plaintext (chat body)

**Use for:** Tiny, conversational replies.

- Greetings, confirmations, errors, one-line status.
- Single fact or **one short paragraph** with no heavy structure.
- Rough guide: **≤ ~400 characters** (configurable via `tools.response_plaintext_max_chars`).

**Do not use** for: lists of many items, tables, JSON, or anything the user should scroll for a long time inside the IM/WebChat bubble.

## 2. Markdown (chat body)

**Use for:** Medium answers that stay readable **inline** in the channel.

- Short bullet or numbered lists (e.g. ≤ ~10 items), small tables, short code snippets.
- Faithful summaries of tool output in **human prose**, not raw dumps.
- Rough guide: **≤ ~2500 characters** (configurable via `tools.response_markdown_ok_max_chars`).

**Do not use** for:

- Raw **JSON** from `web_search`, `daily-brief`, APIs, or `save_result_page` payloads.
- Multi-page reports, full RSS text, or “paste the whole HTML document” replies.

If the content is longer or more structured, use **VMPrint** (below) and return a **link** plus a short summary.

## 3. VMPrint / AST / magazine layout (primary UI for long documents)

**Use for:** Long or **layout-heavy** results — this is the preferred **document UI** for HomeClaw.

- News digests, magazine-style briefings, search roundups with many sources.
- Reports, multi-section summaries, anything that would exceed the Markdown guideline above.

**How:**

1. **Structured digest JSON** (RSS / daily-brief shape, or web search `results` list): `run_skill` on **magazine-render-1.0.0** with `render-daily-brief-ast` and `output_format=browser_preview_html` (Core may also chain this automatically in some fallbacks).
2. **Markdown document:** `render-md` or `save_result_page` with `format='html'` when the pipeline produces HTML suitable for preview.
3. **Reply in chat:** one short summary line + the **view URL** from the tool (do not paste the full HTML/JSON into the message).

VMPrint renders **AST JSON** (layout) in the browser preview; channels show the link; users open the **magazine / preview** page for the full experience.

### Upstream: VMPrint ([cosmiciron/vmprint](https://github.com/cosmiciron/vmprint))

The upstream project has evolved into a full **deterministic document runtime** (not just “a PDF helper”):

- **Preview is the final document** — the same layout session can drive **canvas preview**, **PDF**, and **SVG** export (`@vmprint/preview`), so you do not maintain a separate “print layout” vs “screen layout.”
- **Engine** — spatial simulation layout (`@vmprint/engine`): pagination, tables across pages, multilingual text, reproducible output across Node, browser, and edge runtimes.
- **Contexts** — pluggable render targets (e.g. **Canvas** for in-browser drawing, **PDF** for files); see the modular **contexts** / **font-managers** / **transmuters** split described in the repo README.
- **Draft2Final** — manuscript-style compilation on top of the same API (`@draft2final/cli`).
- **Scripting** — post-settlement hooks (e.g. `onReady`, page counts, TOC-style patterns) so footers and summaries can use **real** settled layout facts.

HomeClaw’s **magazine-render** skill and **`browser_preview_html`** artifacts align with that model: AST → VMPrint → preview link in chat. Keeping VMPrint updated under `tools/vmprint` (see `install.sh` / `docs/tools.md`) pulls in those capabilities as the upstream repo ships them.

For a longer read on the **simulation / “gaming-style” engine**, **why that fits agents**, and what **“UI system” vs “document OS”** means in practice, see [vmprint-ui-runtime.md](vmprint-ui-runtime.md) (section *Gaming technology, AI integration*).

Live browser demo (AST → canvas): [cosmiciron.github.io/vmprint/examples/ast-to-canvas-webfonts/index.html](https://cosmiciron.github.io/vmprint/examples/ast-to-canvas-webfonts/index.html).

## Configuration

In `config/skills_and_plugins.yml` under `tools:`:

| Key | Default | Meaning |
|-----|---------|---------|
| `response_output_policy_in_prompt` | `true` | Inject the short policy into the system prompt for tool-using turns. |
| `response_plaintext_max_chars` | `400` | Guideline threshold mentioned in the injected prompt (plaintext). |
| `response_markdown_ok_max_chars` | `2500` | Guideline threshold for “OK in chat as Markdown”. |
| `web_search_magazine_preview` | `true` | After `web_search`, Core may attach a VMPrint preview link from the same JSON (see `core/llm_loop.py`). |

## Operational notes

- **Channels** may still convert Markdown for outbound (e.g. WhatsApp-style); VMPrint links are plain URLs and work everywhere.
- **Memory / embeddings** stay healthier when chat turns contain summaries + links instead of 10k+ character JSON blobs.
- If local models ignore the policy, **strict fallbacks** and post-processors (e.g. formatting `web_search` JSON, magazine chain after search) still steer behavior; tighten prompts or reduce tool profile scope if needed.
