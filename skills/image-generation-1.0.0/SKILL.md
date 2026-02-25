---
name: image-generation
description: Generate/edit images via Gemini, Baidu Qianfan (通用图像生成), or local Stable Diffusion. Config-driven; auto-selects first available backend (Gemini → Baidu → SD). Text-to-image + image-to-image (Gemini/SD); 1K/2K/4K (Gemini).
keywords: "image generate create draw picture 图片 生成 创建 画图 做图 来一张图"
trigger:
  patterns:
    - "generate\\s+(an?|one)?\\s+image|create\\s+(an?|one)?\\s+image|make\\s+(an?|one)?\\s+image|draw\\s+(a\\s+)?(picture|image)"
    - "创建.*图|生成.*图|画.*图|做.*图|给我.*图|来一张图|弄一张图|生成图片|创建图片"
  instruction: "The user asked to generate or create an image. Call run_skill(skill_name='image-generation-1.0.0', script='generate_image.py', args=['--prompt', '<description>']) first. You may omit --filename; the script uses a unique name per run and saves to the user/companion output folder when run via run_skill. Do not say no image tool is available; do not invent 'Image saved:' — only the run_skill result contains that."
  auto_invoke:
    script: generate_image.py
    args: ["--prompt", "{{query}}"]
---

# Image Generation & Editing

**Response rule:** Only tell the user the image was generated if the run_skill result contains "Image saved:". If the result contains "Error:" or "No image was generated", tell the user that generation failed and quote the error; do not claim success.

Generate new images (or edit with Gemini/Stable Diffusion) using one of three backends, configured in **config.yml** and/or environment variables:

| Backend | Config / env | Notes |
|--------|----------------|------|
| **Gemini** | `GEMINI_API_KEY` or `config.yml` → `gemini.api_key` | 1K/2K/4K; supports `--input-image` |
| **Baidu (Qianfan 通用图像生成)** | `BAIDU_API_KEY` or `config.yml` → `baidu.api_key` | Text-to-image; model/size in config. [Doc](https://cloud.baidu.com/doc/qianfan-api/s/8m7u6un8a) |
| **Stable Diffusion** (local) | `STABLE_DIFFUSION_URL` or `config.yml` → `stable_diffusion.base_url` | e.g. Automatic1111 at `http://127.0.0.1:7860`; txt2img + img2img |

**Provider selection:** In `config.yml`, set `provider: "auto"` (default) to use the first available: Gemini → Baidu → Stable Diffusion. Or set `provider: "gemini"` / `"baidu"` / `"stable_diffusion"` to force one. Override at run time with `--provider gemini|baidu|stable_diffusion`.

When run via `run_skill`, images are saved to the **user or companion output folder** (`output/` under the sandbox); each run uses a **unique filename** unless you pass a specific `--filename`.

## Config (config.yml)

All settings live under the skill folder in `config.yml`. Environment variables override where noted.

- **provider**: `"auto"` (default) or `"gemini"` | `"baidu"` | `"stable_diffusion"`
- **gemini**: `api_key`, `model` (env: `GEMINI_API_KEY`, `GOOGLE_API_KEY`)
- **baidu**: `api_key`, `model` (e.g. `qwen-image`), `size` (e.g. `1024x1024`) (env: `BAIDU_API_KEY`)
- **stable_diffusion**: `base_url`, `steps`, `width`, `height` (env: `STABLE_DIFFUSION_URL`)

See the sample `config.yml` in the skill folder for the full structure.

## Usage

Run the script (e.g. from the skill directory when using run_skill):

**Generate new image:**
```bash
python generate_image.py --prompt "your image description" [--filename "output-name.png"] [--resolution 1K|2K|4K] [--provider gemini|baidu|stable_diffusion] [--api-key KEY]
```

**Edit existing image (Gemini or Stable Diffusion only):**
```bash
python generate_image.py --prompt "editing instructions" [--filename "output-name.png"] --input-image "path/to/input.png" [--resolution 1K|2K|4K] [--provider gemini|stable_diffusion]
```

**Important:** When run via `run_skill`, Core sets `HOMECLAW_OUTPUT_DIR` to the request's output folder. The script saves there with a **unique filename per run** if you omit `--filename` or use a generic name. All backends use REST only (no vendor SDKs).

## Default Workflow (draft → iterate → final)

Goal: fast iteration without burning time on 4K until the prompt is correct.

- Draft (1K): quick feedback loop
  - `--prompt "<draft prompt>" --filename "yyyy-mm-dd-hh-mm-ss-draft.png" --resolution 1K`
- Iterate: adjust prompt in small diffs; keep filename new per run
  - If editing: keep the same `--input-image` for every iteration until you're happy.
- Final (4K): only when prompt is locked
  - `--prompt "<final prompt>" --filename "yyyy-mm-dd-hh-mm-ss-final.png" --resolution 4K`

## Resolution Options (Gemini only)

The Gemini backend supports three resolutions (uppercase K required):

- **1K** (default) - ~1024px resolution
- **2K** - ~2048px resolution
- **4K** - ~4096px resolution

Map user requests to API parameters:
- No mention of resolution → `1K`
- "low resolution", "1080", "1080p", "1K" → `1K`
- "2K", "2048", "normal", "medium resolution" → `2K`
- "high resolution", "high-res", "hi-res", "4K", "ultra" → `4K`

## Credentials and Backends

- **Gemini:** `GEMINI_API_KEY` or `GOOGLE_API_KEY` (or `gemini.api_key` in config), or `--api-key`
- **Baidu:** Single `BAIDU_API_KEY` (or `baidu.api_key` in config). Uses [Qianfan 通用图像生成](https://cloud.baidu.com/doc/qianfan-api/s/8m7u6un8a) (API Key 鉴权).
- **Stable Diffusion:** Set `stable_diffusion.base_url` in config (e.g. `http://127.0.0.1:7860`) or `STABLE_DIFFUSION_URL`. Run your local server (e.g. Automatic1111 with `--api`) so `/sdapi/v1/txt2img` and `/sdapi/v1/img2img` are available.

If no backend is available (no keys/config), the script exits with a clear message listing what to set.

## Dependencies (when run by HomeClaw)

Install in the same Python used by run_skill:

```bash
pip install -r skills/image-generation-1.0.0/scripts/requirements.txt
```

Or: `pip install requests pillow pyyaml`. REST only—no vendor SDKs.

## Preflight + Common Failures (fast fixes)

- Preflight:
  - At least one backend: Gemini key, or Baidu api_key, or Stable Diffusion base_url
  - If editing: `--input-image` points to a real file (Gemini or SD only)

- Common failures:
  - `ModuleNotFoundError: requests` / `pillow` / `yaml` → `pip install requests pillow pyyaml`
  - `Error: No image backend available.` → set credentials for one of Gemini, Baidu, or SD (see Config and Credentials above)
  - Baidu: ensure `BAIDU_API_KEY` (or config `baidu.api_key`) is set
  - Stable Diffusion: ensure local server is running and `base_url` is correct (e.g. `http://127.0.0.1:7860`)
  - "quota/permission/403" → wrong key or quota; try another key or backend

## Filename Generation

Generate filenames with the pattern: `yyyy-mm-dd-hh-mm-ss-name.png`

**Format:** `{timestamp}-{descriptive-name}.png`
- Timestamp: Current date/time in format `yyyy-mm-dd-hh-mm-ss` (24-hour format)
- Name: Descriptive lowercase text with hyphens
- Keep the descriptive part concise (1-5 words typically)
- Use context from user's prompt or conversation
- If unclear, use random identifier (e.g., `x9k2`, `a7b3`)

Examples:
- Prompt "A serene Japanese garden" → `2025-11-23-14-23-05-japanese-garden.png`
- Prompt "sunset over mountains" → `2025-11-23-15-30-12-sunset-mountains.png`
- Prompt "create an image of a robot" → `2025-11-23-16-45-33-robot.png`
- Unclear context → `2025-11-23-17-12-48-x9k2.png`

## Image Editing

When the user wants to modify an existing image:
1. Check if they provide an image path or reference an image in the current directory
2. Use `--input-image` parameter with the path to the image
3. The prompt should contain editing instructions (e.g., "make the sky more dramatic", "remove the person", "change to cartoon style")
4. Common editing tasks: add/remove elements, change style, adjust colors, blur background, etc.

## Prompt Handling

**For generation:** Pass user's image description as-is to `--prompt`. Only rework if clearly insufficient.

**For editing:** Pass editing instructions in `--prompt` (e.g., "add a rainbow in the sky", "make it look like a watercolor painting")

Preserve user's creative intent in both cases.

## Prompt Templates (high hit-rate)

Use templates when the user is vague or when edits must be precise.

- Generation template:
  - "Create an image of: <subject>. Style: <style>. Composition: <camera/shot>. Lighting: <lighting>. Background: <background>. Color palette: <palette>. Avoid: <list>."

- Editing template (preserve everything else):
  - "Change ONLY: <single change>. Keep identical: subject, composition/crop, pose, lighting, color palette, background, text, and overall style. Do not add new objects. If text exists, keep it unchanged."

## Output

- When `HOMECLAW_OUTPUT_DIR` is set (run via run_skill with sandbox): saves PNG there with a **unique name** per run unless you pass a specific `--filename`.
- Otherwise saves to the path given by `--filename` or current directory.
- Script prints `HOMECLAW_IMAGE_PATH=<full_path>` for Core/channels.
- **Do not read the image back**—just inform the user of the saved path.

## Examples

**Generate new image:**
```bash
python generate_image.py --prompt "A serene Japanese garden with cherry blossoms" --filename "2025-11-23-14-23-05-japanese-garden.png" --resolution 4K
```

**Edit existing image:**
```bash
python generate_image.py --prompt "make the sky more dramatic with storm clouds" --filename "2025-11-23-14-25-30-dramatic-sky.png" --input-image "original-photo.jpg" --resolution 2K
```
