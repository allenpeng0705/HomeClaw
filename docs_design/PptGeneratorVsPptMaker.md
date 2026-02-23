# HTML Slides (Skill) vs PPT Generator (Plugin)

## Summary

| | **html-slides** (skill) | **ppt-generation** (plugin) |
|---|--------------------------|----------------------------|
| **Output** | Single HTML file (browser, 9:16 vertical) | PowerPoint `.pptx` (editable, standard) |
| **Style** | 乔布斯风 / 极简 / 科技感 / 竖屏 | Traditional slides (title + bullets) |
| **Invocation** | `run_skill(skill_name='html-slides-1.0.0', ...)` | `route_to_plugin(plugin_id='ppt-generation', capability_id=..., parameters=...)` |
| **Output location** | User/companion **output** folder (via file_write or save_result_page); link returned | User/companion **output** folder; link returned automatically |
| **Use when** | User wants **HTML**, **乔布斯风**, **极简**, **竖屏**, or **单页演示** | User wants **.pptx**, **PowerPoint**, **发给别人**, **传统幻灯片**, or generic "做个PPT" |

## When to Use Which

- **Use ppt-generation (plugin)** when:
  - User says "做个PPT" / "make slides" / "presentation" without specifying style.
  - User needs **.pptx** to edit in PowerPoint or share (email, WeChat, etc.).
  - User says "传统PPT" / "PowerPoint" / "发给客户" / "从文档/大纲生成PPT".

- **Use html-slides (skill)** when:
  - User explicitly wants **乔布斯风** / **极简** / **竖屏** / **单页HTML** / **网页演示**.
  - User wants a single file to open in browser (no Office).

## Routing Guidance (for the model)

1. **Default to ppt-generation** for "PPT", "slides", "演示稿" unless the user asks for 乔布斯/极简/竖屏/HTML.
2. If the user asks for **PowerPoint** or **.pptx** → use **route_to_plugin** with `plugin_id=ppt-generation`.
3. If the user asks for **乔布斯风格** / **极简演示** / **竖屏** / **HTML 演示** → use **run_skill** with `html-slides-1.0.0`.

## Paths

- Skill: `config/skills/html-slides-1.0.0/` (SKILL.md, references, assets, agents).
- Plugin: `plugins/ppt-generation/` (plugin.py, plugin.yaml; **plugin id**: `ppt-generation`).

## Output and links (private, dynamic per user)

- Both save into the **user's private output folder** (or **companion's** when the request is from the companion app). The folder is **dynamic per request**: `base/{user_id}/output/` or `base/companion/output/` (see `docs_design/FileSandboxDesign.md`). This only applies when the sandbox is configured (`homeclaw_root` / file base set in config); otherwise the plugin uses its default directory.
- Core resolves the output path from the **current request context** (same as file tools), so each user gets their own output directory.
- The plugin returns a signed **open link** (Core appends it when the plugin returns `output_rel_path`); the link scope is the same per-user/companion scope so the URL opens only that user's file.
- The skill instructs the model to save HTML to `output/...` (file_write or save_result_page), which resolves to the same private output folder and returns the link to the user.
