# Memory Plugin Migration Guide

HomeClaw Phases 0–3 introduce a pluggable `ContextEngine` and single-slot `MemoryPlugin` system. This document explains how the new architecture maps to existing configuration and what changes, if any, are needed.

## What changed

| Before (legacy) | After (Phase 0–3) |
|---|---|
| Compaction code inline in `llm_loop.py` (~146 lines) | `ContextEngine.compact()` via `_compact_via_engine()` helper |
| Memory backend selected by `memory_backend` only | `memory_plugin` key can override; falls back to `memory_backend` auto-detection |
| No session rotation on compaction | `compaction.rotate_session: true` enables session rotation |
| No hook system | 6 lifecycle hook points (`BEFORE_COMPACTION`, `AFTER_COMPACTION`, etc.) |
| Memory prompt directive hardcoded in llm_loop | `MemoryPlugin.build_prompt_section()` produces directive dynamically |
| MEMORY.md not supported | `config/workspace/MEMORY.md` loaded automatically (shared across agents) |

## Configuration

### `config/memory_kb.yml`

```yaml
# Existing — unchanged
memory_backend: composite   # cognee | chroma | memos | composite

# NEW (Phase 1–2): overrides auto-detection. Leave empty for default.
memory_plugin: ""          # composite | cognee | memos | chroma
```

### `config/core.yml` (or memory_kb.yml)

```yaml
compaction:
  enabled: true
  max_messages_before_compact: 30
  memory_flush_primary: true
  # NEW (Phase 0): enable session rotation on compaction
  rotate_session: false
```

### Memory plugin auto-detection

When `memory_plugin` is empty (default), the system auto-selects:

| `memory_backend` | Auto-selected `MemoryPlugin` |
|---|---|
| `composite` | `CompositeMemoryPlugin` |
| `cognee` | `CogneeMemoryPlugin` |
| `memos` | `MemosMemoryPlugin` |
| `chroma` (or default) | `CompositeMemoryPlugin` (wraps `Memory` base) |

## Backward compatibility

- **All existing `memory_backend` configs work unchanged.** The `MemoryPlugin` system auto-detects the backend.
- **The legacy compaction code path is preserved** as a fallback inside `_compact_via_engine()`. If no `ContextEngine` is registered, the original inline compaction runs.
- **No config migration required.** The new features are opt-in:
  - `memory_plugin: ""` (default) → auto-detection
  - `rotate_session: false` (default) → no rotation

## Health check

```
GET /memory/health
```

Returns:
```json
{
  "ok": true,
  "backend": "composite",
  "index_size": 42,
  "vector_store_ok": true,
  "error_count": 0,
  "doctor": {"ok": true, "issues": [], "fixes_applied": []}
}
```

## New modules

```
core/context_engine/     ContextEngine ABC, legacy engine, registry, session rotation
core/memory_plugin/      MemoryPlugin ABC, slot, 3 adapters (composite/cognee/memos)
core/hooks/              Lifecycle hook system (6 hook points)
```

## New workspace files

- `config/workspace/MEMORY.md` — shared across all agents (OpenClaw pattern)
- `config/workspace/memory/**/*.md` — corpus files, auto-indexed

## For plugin developers

To build a custom `MemoryPlugin`:

```python
from core.memory_plugin import MemoryPlugin, MemorySearchResult, MemoryGetResult

class MyPlugin(MemoryPlugin):
    @property
    def plugin_id(self) -> str:
        return "my-plugin"

    async def search(self, query, *, max_results=5, **kw):
        ...  # return List[MemorySearchResult]

    async def get(self, lookup, *, from_line=None, line_count=None, **kw):
        ...  # return Optional[MemoryGetResult]

    def build_prompt_section(self, *, available_tools=None, citations_mode="inline"):
        ...  # return str
```

Register it:
```python
from core.memory_plugin.slot import register_memory_plugin
register_memory_plugin(MyPlugin(), owner="my-plugin")
```

Set `memory_plugin: my-plugin` in `config/memory_kb.yml`.
