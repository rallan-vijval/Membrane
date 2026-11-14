# Two-agent implementation handoff

The original `IMPLEMENTATION_PLAN.md` defines behavior and acceptance. This document defines branch ownership.

| Owner | Branch | Owned areas |
| --- | --- | --- |
| Backend agent | `feat/membrane-backend` | `backend/`, `contracts/`, `fixtures/`, `scripts/`, Atlas/backend setup docs, `.env.example`, `.gitignore` |
| Frontend agent | `feat/membrane-review-ui` | `frontend/`, `README.md`, UI setup and demo runbook |
| Integrator | `main` | This handoff, cross-branch review, integration verification, final merge |

Use separate worktrees. Do not edit the other owner's files. The backend owns the HTTP contract and sends changes to the frontend before implementation. The frontend uses explicit synthetic fixtures while the API is under construction; real mode never silently falls back to synthetic evidence.

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
