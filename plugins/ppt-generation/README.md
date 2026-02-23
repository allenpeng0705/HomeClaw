# PPT Generation Plugin

Built-in plugin that creates **PowerPoint (.pptx)** presentations. **Plugin id:** `ppt-generation` (use `route_to_plugin(plugin_id='ppt-generation', ...)`). Output is saved to the **user's or companion's output folder** and a link is returned.

## Requirements

- **python-pptx** (in `requirements.txt`). Core installs it with the rest of the stack.

## Capabilities

### 1. create_presentation

Create a deck from **structured input**: title, optional subtitle, and a list of slides (each with title + bullets).

**Parameters (from LLM / route_to_plugin):**

| Parameter         | Type   | Required | Description |
|------------------|--------|----------|-------------|
| main_title       | string | yes      | Title of the first slide. |
| subtitle         | string | no       | Subtitle or tagline on the title slide. |
| slides           | string | yes      | JSON array of `{ "title": "...", "bullets": ["...", "..."] }`. |
| output_filename  | string | no       | e.g. `report.pptx`. Default: derived from main_title + timestamp. |
| language         | string | no       | `en` or `zh` (for future use). |

**Example (LLM can call route_to_plugin):**

- `plugin_id`: `ppt-generation`
- `capability_id`: `create_presentation`
- `parameters`:  
  `{ "main_title": "Q4 Summary", "subtitle": "2024", "slides": "[{\"title\":\"Overview\",\"bullets\":[\"A\",\"B\"]}]" }`

Output is saved to the **user's or companion's output folder** when invoked via Core (so the user gets a shareable link). If `output_dir` is set in config or no request context, files go to workspace `presentations/`. The plugin returns the path; when saved to output folder, Core appends an "Open: &lt;link&gt;" for the user.

### 2. create_from_outline

Create a deck from a **markdown-style outline**: `##` for slide titles, `-` or `*` for bullets.

**Parameters:**

| Parameter         | Type   | Required | Description |
|------------------|--------|----------|-------------|
| outline          | string | yes      | Outline text (e.g. "## Intro\n- Point 1\n## Next\n- A\n- B"). |
| output_filename  | string | no       | Default: from first title + timestamp. |
| language         | string | no       | `en` or `zh`. |

**Example:**

- `capability_id`: `create_from_outline`
- `parameters`:  
  `{ "outline": "## Intro\n- Point 1\n- Point 2\n## Section 2\n- A\n- B" }`

First line can be the main title; second line the subtitle. Then `##` starts each content slide.

### 3. create_from_documents

Create a deck from **one or more documents**: file paths (under workspace or project) or pre-read content.

**Parameters:**

| Parameter          | Type   | Required | Description |
|--------------------|--------|----------|-------------|
| document_paths     | string | no*      | JSON array of file paths, e.g. `["docs/intro.md", "docs/features.md"]`. Resolved under workspace and project root only. |
| document_contents  | string | no*      | JSON array of `{ "title": "...", "content": "..." }` (or `"name"` instead of `"title"`). |
| main_title         | string | no       | Title of the presentation. Default: first document title or first slide title. |
| output_filename    | string | no       | e.g. `from-docs.pptx`. Default: from main_title or timestamp. |
| language           | string | no       | `en` or `zh`. |

\* At least one of `document_paths` or `document_contents` is required.

**Behavior:**

- **document_paths**: Each path is resolved against the workspace directory and the project root; only files under those bases are allowed. File content is read as UTF-8. Markdown is parsed (headings → slide titles, lists → bullets); plain text is split by blank lines (first line = slide title, rest = bullets).
- **document_contents**: Each item's `content` is parsed the same way; `title`/`name` is used as the document/section label.
- Multiple documents are concatenated: first doc can set the main title, then all slides from all docs are added in order. The plugin returns `sources` (list of file names or titles used).

**Example:**

- `capability_id`: `create_from_documents`
- `parameters`:  
  `{ "document_paths": "[\"docs/getting-started.md\", \"docs/plugins.md\"]", "main_title": "HomeClaw Docs", "output_filename": "homeclaw-docs.pptx" }`

Or with pre-read content:  
  `{ "document_contents": "[{\"title\":\"Summary\",\"content\":\"## Overview\\n- Point 1\\n- Point 2\"}]" }`

## Config (config.yml)

| Key              | Description |
|------------------|-------------|
| output_dir       | Optional. When unset and invoked via Core, files are saved to the user/companion output folder and a link is returned. When set (relative or absolute), overrides that and uses this directory. Empty = use request output folder or `config/workspace/presentations`. |
| default_language | `en` or `zh`. |

## Usage from chat

- "Make a PPT about X" → LLM can use **create_presentation** with generated title and slides, or **create_from_outline** if the user pastes an outline.
- "Turn this into slides: ## Intro ..." → LLM uses **create_from_outline** with the pasted text.
- "Generate a PPT from these docs: getting-started.md and plugins.md" → LLM uses **create_from_documents** with `document_paths` (paths under workspace/project).

Files are written under the workspace so the user (or admin) can open them from the server.
