# Agent A — governed memory backend

Branch: `feat/governed-memory-backend`. Base: `9b36508` (planning published on main).

## Contract checkpoint

The canonical DTOs/OpenAPI now specify candidate/revision TTL (3600 seconds default, 60–86400 allowed), strict order/customer scope, independent embedding/memory-search/tracing/vision health, current memory entries, revocation, frozen per-case retrieval, task listing and bounded active-memory execution/reload. See `contracts/README.md` and `contracts/openapi.yaml`. Existing DTO fields remain readable; new fields are additive. New routes are a contract checkpoint and are not ready until their service implementation lands.

User steering: use **DeepSeek** for LLM generation. Agent A owns that change in existing `provider.py` and aggregate config. Current official DeepSeek Responses API documents JSON-schema output and images with `deepseek-flash`; actual key/model capability remains unverified. Agent/vision settings will be independent and default to DeepSeek. Agent C still owns embeddings (Voyage/OpenAI only) and LangSmith; no DeepSeek embedding implementation is requested. No frontend or integrations-owned files will be edited by A.

Next: implement A's domain retrieval/TTL/revocation, consume C's facade when available, extend preflight and tests. Missing application keys remain an external live-validation blocker. No cloud resources have been modified.
