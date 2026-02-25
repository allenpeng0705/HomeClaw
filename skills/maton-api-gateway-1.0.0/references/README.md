# Maton API Gateway — per-service references

These reference files describe **how to access each supported service** via the Maton gateway: API path patterns, common endpoints, and examples. They are copied from [maton-ai/api-gateway-skill/references](https://github.com/maton-ai/api-gateway-skill/tree/main/references).

- **Included:** 113 reference files (one per service: slack.md, hubspot.md, outlook.md, notion.md, google-mail.md, etc.).
- **To refresh** from upstream, run from the repo root:

  ```bash
  python skills/maton-api-gateway-1.0.0/scripts/sync_references.py
  ```

Use these files to know the exact paths and parameters for each service when calling `https://gateway.maton.ai/{app}/{path}` (e.g. Slack: `slack/api/chat.postMessage`, HubSpot: `hubspot/crm/v3/objects/contacts`).
