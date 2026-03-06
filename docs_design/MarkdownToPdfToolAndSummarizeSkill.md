# Markdown-to-PDF Tool and Summarize Skill

This document summarizes the **markdown_to_pdf** tool and the **summarize** skill refinement so that long summaries can automatically become downloadable PDFs.

---

## 1. What was done (step by step)

### Step 1: Tool — `markdown_to_pdf`

- **Where:** `tools/builtin.py`
- **What:** New built-in tool that converts Markdown text to a PDF file and saves it under the user's sandbox (e.g. `output/summary.pdf`). When the path is under `output/`, the tool returns the same kind of view link as `file_write` and `save_result_page` (so the user can open or download the PDF).
- **Parameters:**
  - `content` (required): Markdown string to convert.
  - `path` (required): Relative path for the PDF (e.g. `output/summary.pdf`, `output/report_2024.pdf`).
- **Conversion (priority):** (1) **VMPrint** ([github.com/cosmiciron/vmprint](https://github.com/cosmiciron/vmprint)) when `tools.markdown_to_pdf.vmprint_dir` is set to the clone path (run `npm install` in that dir). (2) **pandoc** on PATH. (3) **weasyprint** (Markdown → HTML → PDF via `markdown` + `weasyprint`). If none is available, the tool returns a clear message.
- **Registration:** Registered in `register_builtin_tools()` next to `get_file_view_link`.

### Step 2: Skill — summarize-1.0.0

- **Where:** `skills/summarize-1.0.0/SKILL.md`
- **What:**
  - **Trigger instruction** updated so that when the summary is long and in Markdown, the model is told to call `markdown_to_pdf` if available and return the PDF link.
  - **New section: "Long summaries → PDF (automatic)"** that tells the model to:
    1. Always return the summary in the reply.
    2. If `markdown_to_pdf` is available and the summary is long, call it with the Markdown and a path like `output/summary_<slug>.pdf`, then include the PDF link in the reply (no need to ask the user first).
    3. If the tool is not available, optionally save as Markdown with `file_write` and return that link.
  - The user does **not** need to say "PDF" or "markdown"; they only ask to summarize. For long results, the PDF link is offered automatically when the tool exists.

### Step 3: Docs

- **docs/tools.md:** Added `markdown_to_pdf` to the file-tools table, mentioned it in the "Reports and file links" bullet, and added a short "Markdown to PDF" section (parameters + dependency options).
- **docs_design/MarkdownToPdfToolAndSummarizeSkill.md:** This summary.

---

## 2. How Core knows the logic

- The **summarize** skill’s SKILL.md is loaded and its trigger + body are available to the LLM (and any RAG over skills). The trigger instruction explicitly says: when the summary is long and in Markdown, call `markdown_to_pdf` and return the PDF link.
- The skill body describes the same flow in "Long summaries → PDF (automatic)". So when the user says "summarize this document" and the model follows the summarize skill, it will:
  1. Produce the summary (e.g. via summarize CLI or document_read + generation).
  2. See that the result is long Markdown.
  3. Call `markdown_to_pdf(content=<summary>, path=output/summary_<slug>.pdf)`.
  4. Include the returned link in the reply (e.g. "PDF saved: [open PDF](link)").

No change to Core’s routing or tool loop is required; the model learns this from the skill text and the tool description.

---

## 3. Usage (operator / user)

**Operator**

1. **Enable tools:** `use_tools: true` in `config/core.yml`.
2. **Use VMPrint (recommended):** Run **`./install.sh`** (macOS/Linux) or **`install.ps1`** (Windows). They clone [VMPrint](https://github.com/cosmiciron/vmprint) into **`tools/vmprint`** and run `npm install` there. Config default is `tools/vmprint` (relative to repo root). To use a different path, set in `config/skills_and_plugins.yml` under `tools.markdown_to_pdf.vmprint_dir`. If VMPrint is not present, the tool falls back to **pandoc** (on PATH) or **pip install markdown weasyprint**.
3. **File sandbox (for links):** Set `file_read_base` (and optionally `core_public_url`, `auth_api_key`) so `markdown_to_pdf` can resolve `output/` and build view links. See [FileSandboxDesign.md](FileSandboxDesign.md).

**User**

- Ask to summarize a document or long text (e.g. "summarize this file", "总结这篇文章"). Do **not** need to say "PDF" or "markdown".
- If the summary is long, the reply will include both the summary text and a PDF link (when the tool and config are in place). Open the link to view or download the PDF.

---

## 4. Summary table

| Item | Location | Purpose |
|------|----------|---------|
| Tool `markdown_to_pdf` | `tools/builtin.py` | Convert Markdown → PDF, save to path, return link for `output/`. |
| Conversion | VMPrint (when `vmprint_dir` set), else pandoc, else markdown+weasyprint | Prefer [VMPrint](https://github.com/cosmiciron/vmprint) via config. |
| Config | `config/skills_and_plugins.yml` → `tools.markdown_to_pdf.vmprint_dir` | Default `tools/vmprint`; install.sh/install.ps1 clone VMPrint there and run npm install. |
| Skill summarize | `skills/summarize-1.0.0/SKILL.md` | When summary is long Markdown, call `markdown_to_pdf` and return PDF link. |
| Docs | `docs/tools.md`, this file | How to enable, install, and use; flow summary. |
