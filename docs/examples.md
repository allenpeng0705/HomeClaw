# Examples

Copy-paste scenarios to learn HomeClaw quickly.

## Example 1: Start Core + WebChat

```bash
python -m main start
python -m channels.run webchat
```

## Example 2: Local + cloud mix mode

In `config/llm.yml`:

```yaml
main_llm_mode: mix
main_llm_local: local_models/your_local_id
main_llm_cloud: cloud_models/your_cloud_id
```

Ask normal questions; HomeClaw routes local/cloud automatically.

## Example 3: Generate a better PDF (VMPrint)

Use tool call style:

```json
{
  "tool": "vmprint_render",
  "arguments": {
    "content": "# Report\n\nYour markdown content...",
    "path": "output/report.pdf",
    "output_format": "pdf",
    "vmprint_profile": "academic"
  }
}
```

Profiles:

- `academic`
- `manuscript`
- `screenplay`
- `literature`

Optional:

- `vmprint_style`

## Example 4: Export AST JSON (for advanced workflows)

```json
{
  "tool": "vmprint_render",
  "arguments": {
    "content": "# Draft\n\nContent...",
    "path": "output/draft.ast.json",
    "output_format": "ast_json",
    "vmprint_profile": "literature"
  }
}
```

## Example 5: Federation basics

1. Set identity in `config/instance_identity.yml`
2. Add peers in `config/peers.yml`
3. In `config/core.yml`, enable federation:

```yaml
federation_enabled: true
peer_call_enabled: false
```

Use Companion for remote-friend messaging across instances.

## Example 6: Troubleshooting commands

```bash
python -m main doctor
python -m main portal
```

In Portal Guide, run VMPrint smoke test for PDF pipeline checks.
