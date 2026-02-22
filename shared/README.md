# shared

Cross-module primitives:

- Model router (OpenAI-compatible + optional LiteLLM path).
- Undo queue backed by SQLite.
- HTTP API client SDK (`NovaAdaptAPIClient`) for core/bridge integrations.
  - Includes transient-error retries with configurable backoff.
- Shared types/utilities for future bridge/vibe/view modules.
