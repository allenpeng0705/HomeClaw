# File-understanding module

This document describes the **file-understanding** module: one stable, robust layer that understands what each file is (image, audio, video, or document) and handles it correctly. It is used in **two ways**: (1) **automatically** when channels send **files** (paths) in the request — Core classifies each file and merges media or injects a short notice for documents; (2) **as a tool** — the model can call **file_understand(path)** to classify a file on demand and get type + path, and for documents get extracted text (so the model can handle "what's in this file?" or "read the file at X" without the user having sent it in this message). **If any step fails, we catch the exception and keep Core running** — no crash.

---

## Summary: how we handle file types from the channel

| Category   | What we do | Typical formats |
|-----------|------------|------------------|
| **Image** | Add path to message as image (or note if model doesn’t support images) | .jpg, .jpeg, .png, .gif, .webp, .bmp, .tiff, .tif |
| **Audio** | Add path to message as audio (or note if unsupported) | .wav, .mp3, .ogg, .webm, .m4a, .flac, .aac, .aiff |
| **Video** | Add path to message as video (or note if unsupported) | .mp4, .webm, .m4v, .mov, .avi, .mkv |
| **Document** | Always inject short notice with paths; model uses **document_read** / **knowledge_base_add** when the user asks to summarize, query, or save. When user sends **file(s) only** (no text) and doc is not too big, we add it to the user's KB directly. | See below |

**Documents we support (text extraction):** We treat as document and extract text for: **plain text** (.txt, .md, .rst, .mdx), **PDF** (.pdf), **Word** (.docx, .doc), **Excel** (.xlsx, .xls), **CSV** (.csv), **HTML** (.html, .htm), **JSON**, **XML**, **PowerPoint** (.pptx, .ppt), **email** (.eml, .msg), **e-book** (.epub). Extraction order: (1) **Unstructured** (when installed: `pip install 'unstructured[all-docs]'`) for all of the above; (2) **pypdf** for PDF if Unstructured fails or is missing; (3) **plain file read** for text-like files (.txt, .md, .csv, .json, .xml, .html). So **plain text, PDF, Word, and CSV** are all supported; Word/Excel and some others need Unstructured for best results. Limit per document: **tools.file_read_max_chars** (default 128000 in config). Unknown extension → we log an error and continue with other files.

**Reuse as a tool.** The same file-understanding logic is exposed as the **file_understand(path)** tool. The model can call it when the user says "what's in this file?", "what type is reports/foo?", or "read the file at X": the tool returns **type** (image | audio | video | document | unknown) and **path**; for **documents** it also returns extracted text (same as document_read). For **image/audio/video** it returns type and path so the model knows what the file is; the model can then use **image_analyze(path)** for images if the user asks to describe. So file-understanding is used both automatically (when the channel sends request.files) and on demand (when the model calls file_understand).

**Tool-based flow.** We always inject only a short notice with file paths (no full document text). The model uses document_read(path), file_understand(path), and knowledge_base_add as needed. **inject only a short notice with file paths** and let the **LLM use tools** to fulfill the user’s intent. The model sees e.g. “User attached: report.pdf (path: channels/matrix/docs/report.pdf). Use **document_read**(path) when the user asks to summarize, query, or edit; use **knowledge_base_add** after reading if they ask to save to their knowledge base.” The model then calls **document_read** (or **file_read**) when the user says “summarize the file I sent”, “what’s in the report?”, or “answer questions about the attachment”, and calls **knowledge_base_add** when the user says “save this to my KB”. No need to inject full document text or to auto-add to KB; the model infers intent and uses tools. **When the user sends file(s) only** (no or negligible text) and the document is not too big: we add the extracted text to the user's knowledge base directly (config **file_understanding.add_to_kb_max_chars**). If the doc is larger than that limit, we skip adding to KB and the user can say what they want later; the model uses document_read as needed.

---

## 1. Goals

- **Support "file" in channel**: Channels send **files** (e.g. `request.files = [path1, path2]`) instead of or in addition to separate `images` / `audios` / `videos`. Core runs file-understanding on `request.files` and merges results into the message.
- **Understand what the file is**: Detect type (image, audio, video, document) from path/extension and optionally magic bytes, then route to the right handling.
- **Proper handling per type**:
  - **Image, audio, video**: Treated like existing media — added to content parts when the main model supports them (image_url, input_audio, input_video), or a short note when not supported. Same as current `images` / `audios` / `videos` flow.
  - **Document (PDF, txt, Word, Excel, etc.)**: Extract text and **inject into the user message** (e.g. "User attached: report.pdf\n\n[extracted text]"). Optionally (future or config): add extracted content to the user's knowledge base.
- **One module, stable and robust**: All steps (detect type, read file, extract text) are wrapped in try/except. On failure we log, record the error in a list, and continue with other files. Core never crashes because of a bad file or missing library.

---

## 2. API

**Input**

- **files**: `List[str]` — file paths (absolute or relative to a configured base, e.g. `tools.file_read_base`). The channel is responsible for saving uploaded files to disk and passing paths Core can read.
- **supported_media**: `List[str]` — from `Util().main_llm_supported_media()` (`["image"]`, `["audio"]`, `["video"]`, or subset).
- **base_dir**: Base directory for resolving relative paths and for document extraction (same as `tools.file_read_base`).
- **max_chars**: Max characters to extract per document (same as `file_read_max_chars` or a default).

**Output (FileUnderstandingResult)**

- **images**: `List[str]` — paths classified as image (to be merged into `request.images` flow).
- **audios**: `List[str]` — paths classified as audio.
- **videos**: `List[str]` — paths classified as video.
- **document_texts**: `List[str]` — extracted text per document file (used when injecting full text or adding to KB).
- **document_paths**: `List[str]` — paths for each document (same order as document_texts); used for short notice and KB source_id.
- **errors**: `List[str]` — one line per file that failed (e.g. "path: could not extract text") so we can log and optionally tell the user.

**Functions**

- **detect_file_type(path: str) -> str**: Returns `"image"` | `"audio"` | `"video"` | `"document"` | `"unknown"`. Uses extension and optional magic bytes (e.g. PDF). Never raises; returns `"unknown"` on error.
- **extract_document_text(path: str, base_dir: str, max_chars: int) -> Optional[str]**: Extracts text from PDF, txt, Word, Excel, etc. (same logic as **document_read** tool: Unstructured, pypdf, plain text). Returns `None` on failure. Never raises.
- **process_files(files: List[str], supported_media: List[str], base_dir: str, max_chars: int) -> FileUnderstandingResult**: For each file: resolve path, detect type, and either add to images/audios/videos or extract text and add to document_texts. On any exception, append to errors and continue.

**Tool: file_understand(path, max_chars?)** — Same logic exposed as a tool the model can call. Input: **path** (relative to tools.file_read_base), optional **max_chars** for documents. Output: **type** (image | audio | video | document | unknown), **path**, and for **documents** the extracted text; for **image/audio/video** a short note (e.g. use image_analyze(path) for images). Never raises; returns an error string on failure. See TOOLS.md / tool registry.

---

## 3. Type detection

| Extension / type | Category   |
|------------------|------------|
| .jpg, .jpeg, .png, .gif, .webp, .bmp, .tiff, .tif | image |
| .wav, .mp3, .ogg, .webm, .m4a, .flac, .aac, .aiff | audio |
| .mp4, .webm, .m4v, .mov, .avi, .mkv | video |
| .pdf, .txt, .docx, .doc, .xlsx, .xls, .md, .mdx, .html, .htm, .csv, .json, .xml, .pptx, .ppt, .eml, .msg, .epub, .rst | document |

Unknown extension → `"unknown"` (we do not add to media or document_texts; we add one line to errors). Optional: magic bytes for PDF (`%PDF`) so we classify by content when extension is missing.

---

## 4. Integration in Core

1. **PromptRequest** has an optional **files: List[str]** (paths). Channels can send **files** instead of or in addition to **images** / **audios** / **videos**.
2. In **process_text_message**:
   - Collect **images_list**, **audios_list**, **videos_list** from `request.images`, `request.audios`, `request.videos` as today.
   - **files_list** = `getattr(request, "files", None) or []`.
   - If **files_list** is non-empty: call **process_files(...)** inside try/except. Merge **result.images/audios/videos** into the message. For **documents**: always inject a **short notice** with file paths and a hint to use **document_read**(path) and **knowledge_base_add**. Paths are relative to **tools.file_read_base** when possible. When the user sent **file(s) only** (no or negligible text) and **knowledge_base** is enabled: add each document to the user's KB only if extracted text length ≤ **file_understanding.add_to_kb_max_chars**; if larger, skip (user can say what they want and model uses document_read). Log **result.errors**.
   - Then continue with the existing logic: build content_parts from images_list/audios_list/videos_list and text_only. If file-understanding raises, catch and continue without file-derived content so Core stays up.

**Stability:** All file-understanding and add-to-KB steps are defensive: config loading, int parsing, result attributes, path handling, and KB add are wrapped in try/except or validated so that bad input, missing config, or KB timeout never crashes Core or the system. Failures are logged and processing continues.

---

## 5. Documents: tool-based flow and add-to-KB when file-only

We **always** inject a **short notice with file paths** (no full document text in the message), so the model uses tools:

- **document_read(path)** / **file_read(path)** — when the user asks to summarize, query, answer questions, or edit (model calls the tool and gets content on demand).
- **knowledge_base_add** — when the user asks to save the file to their KB (model can call document_read first, then knowledge_base_add with the content).

When the user sends **file(s) only** (no or negligible text), we add the extracted document to the user's KB **directly** if the doc is not too big (see add_to_kb_max_chars); if too big, we skip and the user can say what they want later — the model uses document_read as needed. The model infers intent from the user message (“summarize the file I sent”, “save this to my KB”, “what’s in the report?”) and chooses the right tool.

**Config (file_understanding):**

- **add_to_kb_max_chars** (e.g. 50000): when user sends file(s) only (no text), add to KB only if extracted text length ≤ this (chars). If larger, skip. **0** = never auto-add.


---

## 6. Channel / plugin doc folder (downloaded files)

Each **channel** (and optionally each **plugin**) should maintain its **own doc folder** to manage **downloaded files** received from the user. This is the channel’s or plugin’s responsibility; Core does not create or own this folder.

- **Channel**: e.g. `channels/<channel_name>/docs/` (e.g. `channels/matrix/docs/`, `channels/wechat/docs/`). When the platform sends an attachment, the channel saves it under this folder (with a unique name to avoid clashes), then passes the path in **request.files**. The channel is responsible for creating the folder, naming files, and optional cleanup (TTL, max size, etc.).
- **Plugin**: similarly, a plugin may have its own folder (e.g. under the plugin’s directory) for files it receives; it saves files there and passes paths to Core when invoking the same flow.

Paths in **request.files** can be absolute or relative to **tools.file_read_base**; Core resolves them when running file-understanding. The important point is: **each channel/plugin has its own folder for received files** — not shared with other channels. Core only reads the paths it is given.

---

## 7. Knowledge base is user-based

The **knowledge base** is **user-based** (per **user_id**), not per-channel. When we add extracted document content to the KB (e.g. when using the “add to KB” option for file-understanding), we use the **user_id** from the request. So:

- The same user can send files via Matrix, WhatsApp, or email — all extracted content can be added to **that user’s** KB.
- Querying or summarizing “the file I sent” uses the **same user-based KB**; the model finds content by user_id and source_id (e.g. file path). The **channel doc folder** is only for storing the physical files the channel received; the **KB** is for indexed, searchable content per user.

We do not have a “per-channel knowledge base.” Channels share the same user-based KB for a given user.

---

## 8. Channel contract

- **Channel** receives files from the platform (e.g. email attachment, Matrix file, WhatsApp document).
- **Channel** saves each file to disk in **its own doc folder** (e.g. `channels/<name>/docs/`) and passes paths in **request.files = [path1, path2, ...]** (and optionally **request.images** / **audios** / **videos** for explicit media).
- **Core** runs file-understanding on **request.files**, merges media into the message and injects document text, then proceeds as usual. No crash on bad file or missing library. If we cannot understand one file, we log and continue.

See **Multimodal.md** for full channel responsibility (media + files).
