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
- Email
  - `email_send_happy`
  - `email_missing_recipient`

## Existing VMPrint scenarios

- `daily_brief_ast_default`
- `daily_brief_markdown_explicit`
- `weather_pretty_path`
- `stock_pretty_path`

## Notes

- Contracts are now tightened to include key reasons/normalized argv for common flows.
- Further tighten using real-core traces when model/provider behavior changes.
- Prefer invariant checks (call path, normalized args, fallback reason) over wording checks.

