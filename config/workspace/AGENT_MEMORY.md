# Agent memory (curated)

This file is the **curated long-term memory** for the agent. When `use_agent_memory_file: true` in `config/core.yml`, its contents are injected into the system prompt. The agent can append to it via the **append_agent_memory** tool (e.g. when the user says "remember this").

- When both this file and RAG mention the same fact, **this file is authoritative** (see docs_design/SessionAndDualMemoryDesign.md).
- Edit this file manually to add or correct facts. The agent will see your edits on the next request.

You can leave this file empty or add a few initial bullets; the agent will append notes over time.
