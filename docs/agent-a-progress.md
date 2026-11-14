# Agent A — governed memory backend

Branch: `feat/governed-memory-backend`. Base: `9b36508` (planning published on main).

## Contract checkpoint

The canonical DTOs/OpenAPI now specify candidate/revision TTL (3600 seconds default, 60–86400 allowed), strict order/customer scope, independent embedding/memory-search/tracing/vision health, current memory entries, revocation, frozen per-case retrieval, task listing and bounded active-memory execution/reload. See `contracts/README.md` and `contracts/openapi.yaml`. Existing DTO fields remain readable; new fields are additive. New routes are a contract checkpoint and are not ready until their service implementation lands.

User steering: use **DeepSeek** for LLM generation. Agent A owns that change in existing `provider.py` and aggregate config. Current official DeepSeek Responses API documents JSON-schema output and images with `deepseek-flash`; actual key/model capability remains unverified. Agent/vision settings will be independent and default to DeepSeek. Agent C still owns embeddings (Voyage/OpenAI only) and LangSmith; no DeepSeek embedding implementation is requested. No frontend or integrations-owned files will be edited by A.

## Implementation checkpoint

- DeepSeek generation/vision use the OpenAI-compatible Responses SDK with explicit base/key selection, disabled thinking for the bounded decision path, JSON-schema request and local validation. No automatic OpenAI fallback. Raw malformed/incomplete output is retained; only transient failures retry once. Separate OpenAI embeddings remain available only for the preserved v1 profile.
- Governed v2 provides TTL-aware hashes, stable immutable memory identities, exact workspace/order/customer retrieval plus semantic global/preferences, post-filter authority checks, per-case frozen retrieval, stale-expiry rejection, idempotent crash-recoverable revocation, and separate bounded active-memory execution/reload. Wording alone no longer counts as an intended action change.
- Existing and new tests: **89 passed, 2 credential-dependent skips** at the implementation checkpoint. Tests use explicit provider/embedding/Atlas doubles, including DeepSeek request shape, before/after approval/revoke behavior, scope isolation, expiry, raw evidence, revocation during generation and search failure. No live provider success is claimed.
- New setup/preflight preserve v1 data, support the versioned v2 collections/indexes, and report generation/vision/embedding/search readiness independently. `.env.example` selects DeepSeek + Voyage v2; settings retain an explicit v1 compatibility mode. No actual cloud setup ran.

## Handoff dependencies / remaining checks

Agent C's facade branch was not yet published at the last remote check. A does **not** create C-owned files or placeholder production implementations. `integration_bridge.py` lazily imports the facade and reports missing integration clearly. Once C hands over, verify config types/usage/tracing signatures, add its dependency include and regenerate the backend lock, then run combined integration-contract tests. Agent B owns the frontend and consumes the pushed OpenAPI; no frontend files were changed here.

Missing application keys remain an external live-validation blocker: `MONGODB_URI`, `DEEPSEEK_API_KEY`, and the chosen embedding provider key (`VOYAGE_API_KEY` for the v2 example). Optional voice/tracing keys are independent. Verify actual DeepSeek structured output/image capability, document/query Voyage profiles, both real known-neighbor checks, exact approval, active-memory execution/revoke and restart persistence after integration. All API tests so far use explicit doubles. Main remains unchanged.
