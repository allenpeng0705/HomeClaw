# Workflow Scenario Coverage Index

This file tracks workflow-trace scenario coverage by domain.

## Domains and starter scenarios

- Reminder
  - `reminder_happy`
  - `reminder_missing_time`
- File
  - `file_happy`
  - `file_missing`
- Memory
  - `memory_store`
  - `memory_recall`
- Knowledgebase
  - `kb_happy`
  - `kb_miss_fallback`
- Web search
  - `web_search_happy`
  - `web_search_no_results`
- Stock
  - `stock_portfolio_default`
  - `stock_missing_symbol`
  - `stock_monitor_skill_default`
- Email
  - `email_send_happy`
  - `email_missing_recipient`
- Weather (tool-style mock)
  - `weather_pretty_path`
- Weather (skill folder)
  - `weather_skill_default`

## VMPrint / layout scenarios

- `daily_brief_ast_default`
- `daily_brief_markdown_explicit`
- `weather_pretty_path`
- `stock_pretty_path`
- `magazine_render_default`
- `vmprint_ast_layout_default`

## Built-in skills (workflow mock harness)

Each row is a dedicated scenario plus contract asserting `skill_call_started` for the folder name.

- `stock_monitor_skill_default` → `stock-monitor-1.0.0`
- `weather_skill_default` → `weather-1.0.0`
- `magazine_render_default` → `magazine-render-1.0.0`
- `vmprint_ast_layout_default` → `vmprint-ast-layout-1.0.0`
- `ppt_generation_default` → `ppt-generation-1.0.0`
- `ip_cameras_default` → `ip-cameras`
- `desktop_ui_default` → `desktop-ui`
- `summarize_skill_url_default` → `summarize-1.0.0`
- `self_improving_default` → `self-improving-1.2.16`
- `cli_anything_bridge_default` → `cli-anything-bridge-1.0.0`
- `html_slides_default` → `html-slides-1.0.0`
- `x_api_default` → `x-api-1.0.0`
- `social_media_agent_default` → `social-media-agent-1.0.0`
- `openai_whisper_default` → `openai-whisper-1.0.0`
- `meta_social_default` → `meta-social-1.0.0`
- `maton_api_gateway_default` → `maton-api-gateway-1.0.0`
- `linkedin_writer_default` → `linkedin-writer-1.0.0`
- `image_generation_default` → `image-generation-1.0.0`
- `hootsuite_default` → `hootsuite-1.0.0`
- `gog_default` → `gog-1.0.0`
- `baidu_search_default` → `baidu-search-1.1.0`
- `apple_notes_default` → `apple-notes-1.0.0`
- `answeroverflow_default` → `answeroverflow-1.0.2`

## Notes

- Contracts are now tightened to include key reasons/normalized argv for common flows.
- Further tighten using real-core traces when model/provider behavior changes.
- Prefer invariant checks (call path, normalized args, fallback reason) over wording checks.
- In-process mock routes use phrase triggers in `tests/workflow_framework/mock_harness.py`; keep prompts in sync when changing branches.
