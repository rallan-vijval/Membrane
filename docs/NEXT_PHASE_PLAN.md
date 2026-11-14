# Next phase: governed memory and hackathon resources

Status: **PLAN ONLY — no application implementation authorized by this document.**

Shared baseline: `3b456a4` on `main` (integrated backend + frontend). Our branch: `feat/governed-memory-backend` (Agent A). Teammate branches: `feat/governed-memory-ui` (Agent B) and `feat/provider-integrations` (Agent C), each created by its owner from the same baseline. Only planning files change in this checkpoint; `main` stays unchanged. No implementation agents are started by this planning task.

## Goal and priorities

Keep Membrane's screenshot → staged candidate → frozen A/B evidence → explicit review → immutable activation flow. Close the “Memory You Can Govern” gap by retrieving active memories with Atlas Vector Search and enforcing workspace/scope/expiry/revocation. Use partner resources where they improve this flow rather than replacing the working architecture.

Priority order:

1. Governed active-memory retrieval and an observable post-activation task execution.
2. Separate embedding providers and use the advertised Voyage allowance when configured.
3. Frontend memory lifecycle/retrieval evidence and the existing optional ElevenLabs playback.
4. Optional LangSmith tracing after correctness is verified.

Keep FastAPI, direct provider SDKs/PyMongo, React/Vite, and the single leased worker. No LangGraph/Deep Agents/GraphRAG migration, reranker, sample movie data, public deployment, new Atlas resources/tiers, or voice-note ingestion in this phase. Held-out benchmark work stays after connected core acceptance. The PDF is external reference material, not authorization to redeem offers, add payment methods, change sharing, or deploy.

## What the guide changes

- The guide advertises 200M Voyage embedding tokens, $50 LangSmith credits, and an ElevenLabs Creator month with 131K credits. Redemption/account eligibility is unverified; ElevenLabs has an event check-in condition. Do not present advertised offers as available account balances.
- Keep `OPENAI_API_KEY` for agent reasoning and vision. Voyage does not replace those calls. MongoDB plugin authorization is not a Python application credential.
- Choose **direct Voyage embeddings** for the new demo profile to make allowance usage explicit. Atlas Automated Embedding is a possible later alternative, not a simultaneous fallback; do not assume direct Voyage credits cover Atlas-managed embedding billing.
- The integrated v1 currently searches test fixtures but injects a full active snapshot into the agent. Its new API does not yet integrate active-memory expiry/revocation; the preserved legacy implementation contains useful references, not a ready-made replacement for the v1 trust boundaries.

## Three independent tasks and file ownership

| Task | Agent A — memory governance (our side) | Agent B — frontend/demo | Agent C — provider integrations |
| --- | --- | --- | --- |
| Branch | `feat/governed-memory-backend` | `feat/governed-memory-ui` | `feat/provider-integrations` |
| Delivers | Memory retrieval/lifecycle, core APIs, exact freeze/approval integration, active-memory execution, Atlas setup | Lifecycle/retrieval UI, active-task results, existing speech UX, browser checks/runbook | Isolated OpenAI/Voyage embedding clients, provider capability/usage checks, optional LangSmith instrumentation |
| Main dependency | Consumes C's frozen Python interface; publishes HTTP DTOs to B | Consumes A's frozen HTTP contract | Implements the internal interface below; no FastAPI/Atlas dependency |

**Exclusive file ownership (no shared-file edits):**

- **A:** existing `backend/app/*.py` and future memory-governance modules, `backend/app/agent/` and `backend/app/evaluation/` if needed, `backend/tests/` and `backend/pytest.ini`, all `contracts/`, `fixtures/`, existing setup/export/smoke scripts, root `.env.example`/`.gitignore`, `backend/requirements.txt`, `backend/requirements-dev.txt`, `backend/requirements-lock.txt`, backend/Atlas setup/status docs, this phase plan.
- **B:** entire `frontend/` including generated types/adapters, `package.json`, lockfile, Playwright configuration and tests; root `README.md`; `docs/demo-runbook.md`. B never edits the canonical OpenAPI.
- **C:** **new** `backend/app/integrations/` only; **new** `backend/integrations_tests/`; **new** `backend/requirements-integrations.txt`; **new** `scripts/provider_preflight.py`; **new** `docs/integrations-setup.md`. The separate test directory avoids loading A's application fixtures from `backend/tests/conftest.py`. C does not edit existing `provider.py`, `config.py`, FastAPI routes, database code, root requirements/env files, frontend or canonical OpenAPI.

A will add one include of C's dependency file to the core requirements, include C's separate test directory in combined verification, and regenerate the combined backend lock after integration; C alone pins integration-specific direct dependencies in its file. C supplies setting names/defaults to A; only A writes aggregate settings and `.env.example`. Provider-specific documentation stays with C, application/Atlas documentation with A, UI/demo documentation with B. No repository-wide formatting or unrelated cleanup.

Each agent writes progress in its own file (`docs/agent-a-progress.md`, `docs/agent-b-progress.md`, `docs/agent-c-progress.md`). The integrator alone updates `docs/CHANGELOG.md` after handoff. A is the integrator; it does not implement B's or C's assignment on their behalf. This turn writes only the plan/change-log checkpoint.

All three can start independently against the interfaces in this plan. **First implementation checkpoints:** A publishes HTTP DTOs/OpenAPI and validated synthetic examples for B; C publishes its Python interface and contract tests for A. Review those small contract-only commits before wiring dependencies. B can build components with explicit mocks; A can develop domain logic with explicit test doubles; C can implement/test adapters without application or Atlas imports. No runtime mock fallback is introduced. Schema/interface publication belongs to future implementation, not this planning-only turn. Breaking changes require owner review and updated examples; never edit another owner's interface to make a local build pass.

### Frozen A ↔ C internal interface

C owns `backend/app/integrations/api.py` as its public facade; A imports only that facade, not SDK internals. The facade must not import `Settings`, `Store`, FastAPI, the runner or policy modules.

- `EmbeddingConfig`: immutable configuration with `provider`, `model`, `dimensions`, secret `api_key`, `timeout_seconds`, `max_retries=1`; its repr/logs exclude the secret. A constructs it from aggregate settings.
- `create_embedding_client(config, semaphore)` → client supporting `embed_documents(texts)`, `embed_query(text)`, `describe()` and an explicitly billable `probe()`. A supplies the shared bounded semaphore; C does not create another unconstrained call pool.
- `EmbeddingBatch`: `vectors`, `profile_id`, provider/model/dimensions, input type, input tokens when reported (nullable otherwise), attempted calls and elapsed milliseconds. `embed_query` returns the same shape with one vector. `describe()` returns redacted metadata with a deterministic profile ID derived from provider/model/dimensions/input conventions, never credentials.
- `IntegrationFailure`: sanitized `code`, `message`, `retryable`, attempted-call count; no raw provider exception/key in its string. A maps it to existing API errors/health/inconclusive evidence. C retries only transient provider failures once and validates dimensions; A does not retry the adapter again.
- `create_tracer(config)` → `span(name, metadata)` context manager. The yielded handle provides `set_outputs(redacted_metadata)` and nullable `trace_url`; disabled/failed tracing is a no-op and never throws into application flow. A supplies identifiers and redacted outcomes, not raw prompts/screenshots or API keys.
- `probe()` verifies configured embedding access/dimensions, returns redacted status/usage, and never reads/writes Atlas. Automatic health reads use cached results/configuration; they do not make paid probes.

These signatures and semantics are the seam: C owns provider errors/retries/usage; A owns persistence, policy, admission and HTTP readiness; B owns presentation. Contract tests exercise both sides of this seam before final merge.

## Task A — backend/data implementation

### A1. Wire the isolated embedding integration into the application

- Consume C's embedding facade for fixture and active-memory indexing/querying; remove the application's assumption that embedding and generation use the same provider. Keep existing OpenAI text/vision generation in A-owned `provider.py`.
- A owns `EMBEDDING_PROVIDER=openai|voyage`, selected keys/models/dimensions in aggregate settings and redacted HTTP health. Retain OpenAI as the code default for existing configurations. The new demo setup example selects `voyage`, `EMBEDDING_MODEL=voyage-4`, `EMBEDDING_DIMENSIONS=1024`, and server-only `VOYAGE_API_KEY`.
- No automatic provider fallback or double retry. Surface C's dimension/profile failures and actual usage. Independent generation and embedding readiness is mandatory. Pass A's existing semaphore/timeouts to C.
- New demo setup uses `WORKSPACE_ID=membrane-demo-v2`, collection `task_fixtures_v2`, and index `fixture_semantic_v2`. Memory entries use `memory_entries_v2` and `memory_semantic_v1`. Versioned collections prevent mixing the old 1536-dimensional vectors with new 1024-dimensional vectors. Preserve legacy `task_fixtures`, both existing Search indexes, v1 versions/runs, and unrelated sandbox data.
- Make seed/index/preflight commands explicit about the selected profile and new collection names. Seed the same 24 development/12 held-out fixtures idempotently. Index filter fields must support the actual workspace/split or memory-membership query predicates. Run real known-neighbor checks for fixtures and memories; search failure never produces a passing empty suite.
- Store a profile identifier derived from provider/model/dimensions/input conventions on embeddings and frozen runs. Query and document profiles must match. No automatic backfill or deletion of v1 data. Existing records remain readable; new governed-memory testing/approval is enabled only after the v2 workspace has been initialized and its indexes verified.

### A2. Immutable memory identity, scope, expiry and revocation

- Give newly activated memory entries stable string `memory_id`s, content hashes, originating candidate/version IDs, activation time, scope, and `expires_at`. Entry documents are immutable; active membership comes from the authoritative version snapshot.
- Add `ttl_seconds` to candidate creation/revision, default 3600, integer range 60–86400. Include it in candidate content hashing and frozen run evidence. Revision creates a new candidate; changing TTL never mutates prior evidence. Set entry `expires_at = activation_time + ttl_seconds`, independently of trusted exception expiry.
- Order scope requires exact nonempty order/customer IDs. An exception reference must resolve against server-owned authority; it grants nothing by itself. Global/preference entries cannot carry order/customer/exception identifiers. Keep workspace identity backend-controlled; never accept workspace/verification authority from source text or candidate bodies.
- Revocation creates a new immutable version without the targeted memory and atomically compare-and-sets the active pointer. Append an idempotent review event using the existing recoverable receipt approach. Never overwrite the original version, delete evidence, or use MongoDB TTL deletion to implement logical memory expiry.
- Effective memory excludes entries whose expiry is at or before the evaluation timestamp, and any entry absent from active membership. Historical snapshots remain inspectable and clearly labeled. A repeated identical revoke with the same key is safe; stale base or an already-removed entry under a new request returns a clear 409.

### A3. Real memory retrieval without corrupting A/B comparison

- For each selected task, freeze the active version and a single `retrieval_at` timestamp. Build the eligible ID set from that version, workspace and expiry. Maximum demo snapshot is 100 memory entries; refuse further admission with a clear limit rather than silently truncating authority/history.
- Retrieve exact order/customer-scoped entries deterministically from Atlas using eligible IDs. Retrieve up to six global/preference entries using an actual vector query with workspace, eligible-ID membership and scope filters (`numCandidates=100`). Union/deduplicate exact and semantic results; order deterministically by activation time then ID. Record reasons and semantic scores, using null scores for exact-scope inclusion.
- Recheck returned documents against authoritative membership, workspace, expiry, content hash and scope after search; search-index lag must not resurrect revoked entries. An empty successful query with no relevant eligible entries is legitimate; an unavailable/mismatched index is not. Exact entries must not disappear because semantic top-k excluded them.
- Freeze each case's resulting base memories once, reuse the identical base for both sides and both repetitions, and persist retrieval evidence. View B adds only the frozen staged candidate. Keep that candidate visible across the admission suite as untrusted test data so out-of-scope behavioral regressions remain detectable; do not conceal them by filtering the candidate out of test cases. Active-memory scope filtering applies to approved memory retrieval.
- Preserve the five sentinels/four semantic fixture results/three deterministic neighbors, 12 distinct cases, 48 executions, deterministic tool enforcement, positive learning obligation, and all current failure/budget rules.
- If the active pointer changes while preparation is freezing its inputs, discard the partial suite as stale/inconclusive and require retest. Once frozen, runs do not reread changing memory per execution. Approval rechecks the exact base, candidate+TTL hash, policy/exception authority and that retrieved base memories have not expired since testing. Revocation or expiry must invalidate stale approval evidence.

### A4. Demonstrate behavior after activation

- Add a bounded active-memory task execution endpoint using an existing enabled development fixture. No arbitrary tools, customer payloads or real refunds. Require an explicit active `base_version_id`; freeze/retrieve memory as above, run one real structured model decision with at most one transient retry, enforce the simulated refund policy, and persist evidence separately from admission runs.
- Return actual retrieved IDs/reasons/scores, raw response, parsed attempt, enforcement, checks, usage, timing and source version. Revalidate authority immediately before simulated tool enforcement. This execution cannot activate a candidate or serve as admission evidence.
- Use an independent per-execution maximum of two attempted generation requests. Record retrieval embedding usage separately; do not consume or disguise the admission suite's model-call counter. Use this endpoint to show order 4821 before activation, after approval, and after expiry/revocation, with a neighboring unrelated task unchanged.

### A5. Tracing hooks and credential boundaries

- A adds `LANGSMITH_TRACING=false` and server-only `LANGSMITH_API_KEY` to aggregate settings, then calls C's safe tracing facade around retrieval/executions/checks. A persists optional trace URLs with workspace/run/case/side/repetition/profile metadata; C owns vendor SDK behavior.
- Atlas remains authoritative. Do not let tracing alter admission, block persistence, cause an extra model invocation, or become required for success. Pass identifiers/redacted outcomes only. No framework migration.
- Continue independent implementation with missing credentials, but report connected checks separately. Do not redeem offers, add payment methods, modify Atlas network access/tier, or assume advertised credit balances. Existing ElevenLabs service remains optional and independent of admission.

## Task B — frontend/demo implementation

- Consume the canonical contract commit and regenerate `frontend/src/api/generated.ts`; keep UI view models separate with explicit typed adapters. Preserve existing screenshot, stage, revision, run, review and history behavior.
- Add a governed-memory panel listing current membership, stable IDs, order/customer scope, expiry time, effective availability and source lineage. Show expired entries as excluded, not active context. Use backend `evaluated_at`/availability as authority; a client countdown may be informational only. Refresh after approval/revoke and when an expiry boundary is reached.
- Add lifetime selection to staging/revision (default 60 minutes; range 1–1440 minutes converted to seconds). Preserve TTL with scope/exception reference across editing and revisions. Changing fields is not a mutation of historical evidence.
- Add a revoke control for each effective current entry, a required reviewer reason, a stable per-operation idempotency key and explicit base version. Display stale/revoked responses and refresh authoritative state. Do not add a force-approve, arbitrary workspace selector or secret-entry form.
- In run details, distinguish **test-case selection** from **agent-memory retrieval**. Show each case's frozen retrieved IDs/text/scope/expiry/reasons/scores and the candidate overlay separately. Preserve raw attempts, both repetitions, policy judgments and live/recorded/synthetic labeling.
- Add an “Run with active memory” panel selecting an enabled development fixture. It calls only the bounded active-memory endpoint and displays its exact result, retrieval evidence, simulated-tool outcome and version. Keep these executions visually separate from admission eligibility.
- Keep ElevenLabs exact-answer playback and clear configured/disabled/error states. No voice-note upload, speech-based approval, cloned voices or autonomous voice agent in this phase. Never present an advertised 131K allowance as a real remaining balance.
- Add optional LangSmith trace links only when the backend supplies them. Hide absent links; tracing outages must not appear as admission failures. No LangSmith credentials in Vite variables.
- Extend explicit synthetic fixtures and browser tests for TTL/revoke/retrieval/live-task views; banner stays present and mock mode never activates itself on real service errors. Update root README and demo runbook to demonstrate actual observations and clearly separate missing credentials from passing local checks.

## Task C — provider integrations, independently testable

### C1. Embedding adapters and explicit credit usage

- Implement only the owned integrations package and frozen facade. Support OpenAI embeddings for existing profiles and direct Voyage embeddings for the new profile; do not modify the existing text/vision provider. Prefer the official Voyage SDK, pin a successfully tested version in `backend/requirements-integrations.txt`, and preserve the OpenAI SDK version used by A unless a coordinated change is necessary.
- For Voyage use `voyage-4`, dimension 1024, `input_type=document` for indexed descriptions/memories and `input_type=query` for queries. Use nontruncating requests so overlength inputs fail visibly. Validate returned vector count and actual dimension. Return actual reported token usage; unknown cost remains null, never an invented dollar amount.
- Missing/invalid keys, unsupported model/profile, dimensions, quota, timeouts and transient errors yield sanitized typed failures. Retry transient errors once within the supplied semaphore and timeout; count every attempted provider request. Do not fall back, contact Atlas, or change collection/index configuration.
- Supply explicitly opt-in `scripts/provider_preflight.py` for provider access/dimension tests and sanitized usage. It reads application environment values independently through the facade config, never imports A's app/database, and does not redeem offers or add payment methods. Tests use fake SDK transports; real probes require credentials and an explicit billable invocation.

### C2. Optional LangSmith tracing

- Implement `create_tracer` as a disabled-by-default no-op wrapper unless configured. When enabled, use LangSmith instrumentation directly around custom spans; no LangChain/LangGraph/Deep Agents runtime is required.
- Use nonblocking enqueue to a bounded background trace queue (256 events; drop tracing events when full). Vendor submission has a two-second timeout, no retries, and shutdown flush waits at most two seconds. Handle initialization/submission/flush failures internally. No model re-execution, admission changes, database calls or raw secret-bearing exception text. Do not auto-wrap the OpenAI client in a way that changes retry semantics or uploads full prompts by default.
- Propagate stable application IDs in metadata and provide a nullable verified trace URL when the SDK supplies enough information. Missing trace links must remain null; do not fabricate success. Add unit tests for disabled mode, nesting, redaction, callback failure and submission failure.
- Document key setup, advertised credit eligibility versus verified balances, provider-specific probes and metadata-only tracing in `docs/integrations-setup.md`. ElevenLabs changes are out of C's scope: existing backend playback stays with A and frontend controls with B.

## Contract checkpoint — intended interfaces

Agent A formalizes these in OpenAPI before HTTP implementation; Agent B must not invent additional fields. Existing endpoints and error envelopes stay compatible where possible.

| Interface | Planned addition |
| --- | --- |
| `CandidateIn`, `ReviseIn`, `Candidate` | `ttl_seconds` (default 3600, range 60–86400); freeze/hash includes lifetime |
| `GET /api/health` | Independent `embeddings`, `memory_search`, `tracing` component statuses/reasons; existing components retained |
| `GET /api/memory/entries` | `{version_id, evaluated_at, items, truncated}`; each item has memory ID, text/hash, scope, candidate ID, activated time, expiry and availability `active|expired`; history retains revoked entries in their old versions |
| `POST /api/memory/entries/{memory_id}/revoke` | Body `{base_version_id, reason}` plus `Idempotency-Key`; returns `{version_id, event_id}`; 409 for stale/conflicting requests |
| `Run.memory_retrieval` | One record per selected case: `{case_id, retrieval_at, profile_id, base_version_id, entries}`; entries carry ID/text/hash/scope/expiry/reason/nullable score |
| `GET /api/tasks` | `{items, truncated}` with enabled development fixture IDs and synthetic descriptions only; exclude held-out fixtures and expected answers |
| `POST /api/agent/tasks/{fixture_id}/execute` | Body `{base_version_id}`; returns execution ID/version/retrieval evidence, existing `Execution`-shaped result, config/usage and optional trace URL; never admission eligibility |
| `GET /api/agent/executions/{execution_id}` | Reload the stored active-memory execution without another provider call |
| Audit events | Add `revoke`; return targeted `memory_id`, source base/new version and reviewer reason. Keep old event shapes readable using nullable additive fields |
| Trace links | Optional nullable `trace_url` on run/execution evidence; frontend never constructs a vendor URL from an ID |

Keep `Version.memories` and historical v1 records readable; new v2 entries include the additional governed fields. Do not rewrite historical evidence to fabricate missing retrieval provenance. UI labels older runs “retrieval provenance unavailable” rather than inferring it. Old v1 passing runs cannot authorize new v2 mutations/activation; retest under the v2 profile.

## Acceptance and merge gates

**Agent A tests:** integration facade wiring and profile propagation; independent generation/embedding readiness; workspace/order/customer exclusion; global top-k plus exact-scope inclusion; no held-out selection; expiry equality boundary; no resurrection after index lag/revoke; frozen identical base retrieval for A/B/repetitions; candidate-only overlay; TTL hash/stale-expiry approval rejection; idempotent/concurrent/crash-retry revocation; active-task evidence cannot admit memory; tracing failures cannot change results; all current policy/isolation/activation tests retained.

**Agent B tests:** canonical DTO adapters; lifetime/reference preservation; expired/revoked display and stale responses; matching retrieval evidence on both sides; active-task execution and reload; stable decision keys; missing trace/voice states; no silent synthetic fallback; desktop/mobile/keyboard review flow; typecheck/build and generated-type consistency.

**Agent C tests:** document/query mode and nontruncation parameters; vector count/dimension/profile checks; missing/invalid credentials, model mismatch, quota/timeout and one transient retry; semaphore participation; actual usage/call accounting; no fallback or Atlas imports/writes; safe exception redaction; optional tracing never throws or causes another model call. These tests run without A's app and without B's frontend.

**Connected joint gate:** real Voyage embeddings → real Atlas fixture and memory known-neighbor queries → source extraction → staged broad/scoped tests with actual observed results → exact approval → active-memory task result → revoke/expire → changed retrieval/behavior on the next execution → reload/restart persistence. Confirm another workspace and another order do not receive the scoped memory. All tools remain simulated. Missing credentials/search capability blocks this live gate, not independent coding.

Agent A alone owns shared sandbox writes and runs setup/connected checks once. B uses HTTP fixtures until endpoints are ready; C uses SDK transport doubles and opt-in provider probes, never shared database fixtures. No concurrent reseeding/reindexing. Optional LangSmith/ElevenLabs checks require configured eligible accounts and do not block the core gate.

**Integration order:** merge C's isolated integration package first, then A's application/governance wiring, then B's UI. Before merging, all three hand over commit IDs, owned-file changes, checks, setup variables and blockers. A verifies the Python seam, aggregate dependency lock, generated HTTP contract/client compatibility and combined suites. A alone updates the shared change log and pushes reviewed main. No source-branch rebases/force pushes on teammates. Each later split starts from the same verified checkpoint.

## Planning source references

Resource guide reviewed: `[EXTERNAL] AGENTS IN CONTEXT TORONTO_ A MONGODB HACKATHON RESOURCE GUIDE.pdf` (user-supplied, November 14). The guide's submission requirements are preparation items, not permission to change repository visibility, submit externally or deploy.

- Voyage document/query modes and dimensions: https://docs.voyageai.com/docs/embeddings
- Atlas automated embedding alternative: https://www.mongodb.com/docs/vector-search/crud-embeddings/automated-embedding/
- LangSmith instrumentation without a framework migration: https://docs.langchain.com/langsmith/annotate-code
