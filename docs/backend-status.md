# Agent A handoff status

Branch: `feat/membrane-backend`. Worktree: `C:\MongoDB\membrane-backend`.

Coordination: teammate readiness was confirmed and both branches are integrated on main. See `CHANGELOG.md` for source commits, semantic integration fixes and combined checks. Split future work from the same updated `origin/main`; retain the original feature branches as history.

## Implemented

- Versioned FastAPI/Pydantic HTTP contract, error envelope, upload and local asset serving, source extraction provenance, candidate staging/revision, active-memory/history APIs.
- Direct OpenAI structured-decision/vision/embedding adapter with bounded retries, call accounting and concurrency; one fresh isolated decision per case/side/repetition.
- Workspace-scoped Atlas persistence, non-destructive indexes/seed, 24 development/12 held-out fixtures, five sentinels plus four real semantic neighbors plus three deterministic neighbors and stable dedup/fill.
- Frozen selection/task/memory/policy/exception/config/prompt/schema evidence, leases, resumable case checkpoints, MongoDB summaries and visible incomplete/error/budget outcomes.
- Deterministic simulated-refund policy, useful order-specific learning check, attempted-action preservation even on guard rejection, baseline violations and observed violations despite partial errors.
- Exact-evidence review, idempotency, immutable prepared versions and atomic active-pointer CAS with crash-recoverable audit receipt; unactivated prepared versions excluded from history.
- Optional exact-answer ElevenLabs TTS with matching voice settings, caching, workspace character limits, local audio and Atlas metadata. No voice-generated authority or approval.
- PowerShell setup docs, actual Search index JSON/UI fallback, preflight, API smoke script, synthetic screenshot, generated OpenAPI, pinned dependencies, deterministic tests.

## Verified locally

`python -m pytest backend/tests tests -q`: **60 passed, 2 skipped**. Skips are the new opt-in real integration test and the legacy Atlas governance module because credentials are absent. Tests use explicit provider/database doubles; they do not establish live integration success.

OpenAPI regeneration and Python compilation pass. `git diff --check` passes. Preflight was run without secrets and correctly returned unavailable database/model/search and nonzero exit status. The HTTP tests need Windows socket permissions outside the execution sandbox because its socketpair implementation blocks inside the sandbox.

## Remaining external acceptance

Populate local ignored `.env` with `MONGODB_URI`, `OPENAI_API_KEY`, and accessible `AGENT_MODEL`/`VISION_MODEL` IDs. Then seed with real embeddings, create/verify `fixture_semantic_v1`, run preflight, and run the billable API smoke against the started server. Verify active state after a service restart. Configure ElevenLabs only if using voice and verify promotional credit eligibility separately.

Read-only plugin access has been verified, but application-driver write/read, real model runs, known-neighbor retrieval through the application, paid TTS, and live restart acceptance remain **unverified**. No sandbox data or infrastructure was changed during implementation.

The teammate's frontend is now integrated, with generated wire types, explicit DTO adapters and six passing browser checks. The review flow uses synthetic HTTP test fixtures; an unmocked check reaches actual local FastAPI health through the proxy. Use `contracts/README.md` and `contracts/openapi.yaml`; the new API entrypoint is `backend.app.main:app`, not the preserved legacy `membrane.app:app`. M5 benchmark execution/export remains deferred until the core connected demo passes, as required by the milestone order.
