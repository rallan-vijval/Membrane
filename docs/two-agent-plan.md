# Two-agent implementation handoff

The original `IMPLEMENTATION_PLAN.md` defines behavior and acceptance. This document defines branch ownership.

**Coordination update — November 14:** Finish the current handoff on the existing branches, wait for the teammate's readiness confirmation, merge both contributions into `main`, then create the next separate branches from that shared commit. Do not start a new split or merge early. Read `docs/CHANGELOG.md` for commit IDs/change locations and `docs/merge-checklist.md` for the integration gate. This update supersedes the initial branch-start instructions below.

| Owner | Branch | Owned areas |
| --- | --- | --- |
| Backend agent | `feat/membrane-backend` | `backend/`, `contracts/`, `fixtures/`, `scripts/`, Atlas/backend setup docs, `.env.example`, `.gitignore` |
| Frontend agent | `feat/membrane-review-ui` | `frontend/`, `README.md`, UI setup and demo runbook |
| Integrator | `main` | This handoff, cross-branch review, integration verification, final merge |

Use separate worktrees. Do not edit the other owner's files. The backend owns the HTTP contract and sends changes to the frontend before implementation. The frontend uses explicit synthetic fixtures while the API is under construction; real mode never silently falls back to synthetic evidence.

Agent A is implementing the backend. Agent B is reserved for the teammate's agent; no frontend implementation is supplied by Agent A. Create `feat/membrane-review-ui` from current `main` in your own clone/worktree. Start the frontend independently and consume the backend contract as soon as it lands on `feat/membrane-backend`.

## Shared HTTP contract

Agent A publishes `contracts/openapi.yaml` and examples as the interface authority. All paths use `/api`, string IDs, snake_case JSON, UTC ISO timestamps, integer cents, explicit nullable fields, and `{error: {code, message, details}}` errors. Backend config fixes the workspace and labeled demo reviewer. The browser cannot create trusted exceptions or verification facts.

- Candidate states: `staged`, `testing`, `eligible`, `quarantined`, `inconclusive`, `approved`.
- Run states: `queued`, `running`, `completed`, `failed`, `inconclusive`.
- Admission: `eligible`, `quarantine`, `inconclusive`, or null while pending.
- Sides: `baseline`, `candidate`; repetitions: 1 and 2.
- Health statuses: `ready`, `unavailable`, `degraded`, `disabled`, separately for database/model/search/voice.
- Upload: multipart `file` at `POST /api/sources`; response includes extracted text, quotation, proposed candidate/scope, provenance, and image URL. `GET /api/sources/{id}/image` serves the image.
- Candidates: create/list/detail, child revision, run creation, quarantine, approval as in the original specification. Creation requires `source_id`, `text`, structured `scope`, `base_version_id`.
- Run creation returns 202 and `run_id`. Run detail includes frozen selected fixtures/reasons/scores, progress out of 48 executions, both sides/repetitions, raw attempts, exact tool arguments, enforcement, check reasons, errors, model configuration and usage.
- Reviewer actions require `Idempotency-Key`. Approval references the exact `run_id`; stale evidence returns 409 and needs retesting.
- Active memory/history return version lineage and append-only reviewer events. Lists return at most the latest 100 with `truncated`.
- Optional audio: `POST /api/runs/{id}/cases/{case_id}/audio` takes `{side, repetition}`, synthesizes only exact stored answer text, and returns transcript plus a backend-served audio URL.

Agent B generates TypeScript types from the published contract and keeps synthetic HTTP fixtures inside `frontend/`. Any breaking API change requires coordination; Agent A owns edits to the canonical contract.

## Agent A deliverables

1. M0: config validation, redacted readiness, Atlas/application/model/search checks and setup instructions. Preserve existing Atlas data.
2. M1: schemas, workspace-scoped indexes, idempotent seed (24 development and 12 held-out fixtures), trusted exceptions, refund policy validator, screenshot upload/extraction, candidate lifecycle.
3. M2: real Vector Search plus sentinels/neighbors, frozen isolated A/B execution, two repetitions, bounded calls/retries, persistent results, checks/classifications/admission, progress, MongoDB summaries.
4. M3/M4: revisions, idempotent decisions, hash/base/policy validation, atomic version activation, leases/checkpoints, restart/crash recovery, visible history.
5. Optional ElevenLabs service: exact-answer TTS, shared voice settings, local cache/files and Atlas metadata, quota/length bounds and independent readiness. No voice-note ingestion or live voice agents in this MVP.
6. M5 only after core integration: frozen held-out benchmark, strategy comparison, Markdown/JSON export.

Backend tests cover policy scope/identity/destination/amount/expiry/duplicates, injection, memory isolation, A/B parity, guarded attempts, search failure/filters/dimensions, admission errors, stale/concurrent/idempotent/crash-retry approvals, and optional audio invariants. Tag real integration tests separately. Agent A is the sole Atlas writer and final integrator.

## Agent B deliverables

1. React + TypeScript + Vite; accessible responsive three-column review UI, local `127.0.0.1:5173` with `/api` proxy to `127.0.0.1:8000`.
2. Header: active version and independent integration health. Left: screenshot, actual extraction, source trust, editable candidate/scope and lineage.
3. Center: selected cases/reasons/scores, two-second run polling, paired attempts, both repetitions, readable JSON/tool enforcement and classification. Stop polling at terminal status or page departure.
4. Right: eligibility/reasons, quarantine/revise/approve. Approval requires backend eligibility; 409 prompts retesting. Footer/drawer: history, run/model/config, calls/tokens/latency, live versus recorded badge.
5. Store selected candidate/run IDs in URL for reload. Never treat frontend state as authoritative active memory. Synthetic mode requires explicit opt-in and persistent label; real mode never silently falls back.
6. Optional audio controls use backend readiness and exact transcripts. Audio failures cannot disable review. No spoken approval.
7. Frontend typecheck/build and browser smoke/mock contract scenarios. Own frontend lockfile, UI setup docs, README PowerShell instructions and three-minute demo runbook. Leave backend/root config to Agent A.

## Merge procedure

Agent B can build against contract fixtures immediately and connect to Agent A's API at each checkpoint. Each agent commits only owned files and reports commit IDs plus verification. Merge backend first, then frontend; Agent A fixes backend integration issues and Agent B supplies frontend fixes. Avoid unrelated formatting and shared root dependency files. Do not use separate in-memory/SQLite application storage as a substitute for Atlas.

## Integration checkpoints

1. Freeze API schemas, enum values, errors, paired-result structure, and reviewer idempotency.
2. Connect health, screenshot upload, staging, and active memory.
3. Connect persisted run progress, selection provenance, paired attempts, and policy judgments.
4. Connect quarantine, child revisions, exact-run approval, version history, and reload.
5. Add optional ElevenLabs playback of stored answer text, independent of admission.
6. Merge backend then frontend, run Python tests, frontend typecheck/build, and browser smoke. Report real external checks separately from deterministic mocked tests.

## Credentials and external state

Secrets belong in a local ignored `.env`, never commits. The application needs `MONGODB_URI` and `OPENAI_API_KEY`; ElevenLabs is optional. An Atlas plugin connection is not an application credential. Placeholder configuration must allow development and show unavailable integrations accurately.

Read-only plugin inspection on November 14, 2026 confirmed the sandbox's `Cluster0` is available and database `membrane` exists. Existing collections are `sources`, `memory_versions`, `simulation_runs`, and `task_fixtures`. Existing `fixture_vec` is a queryable auto-embedding Search index on `message`, with a `tenant_id` filter. Preserve those resources. Application schemas, workspace IDs, embeddings, and the planned Search index must be validated separately.

## Completion gate

The full live flow requires real application credentials: screenshot extraction, staged candidate, real Atlas retrieval, isolated paired model calls, persisted evidence, quarantine/revision, exact eligible approval, reload and restart persistence. Missing credentials must be reported as a blocker, never replaced with a claimed live success. Do not fabricate a model regression if the broad candidate is resisted.
