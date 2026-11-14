# Team change log

Read this first when joining the project. Dates use America/New_York. Append an entry for each handoff, contract change, integration fix, or merge; include branch, commit, verification, and any action needed by the other agent. Never include secrets or claim mock results are live.

## 2026-11-14 — Both agents integrated and verified on main

**Current state:** teammate readiness confirmed by the user. Backend `d5e4c73` merged in `5e58293`; frontend `f061fe8` merged in `25a804c`. There were no Git file conflicts. The commit containing this entry fixes the semantic API mismatches found during integration. The older pre-merge entry below is historical.

### Integration changes

- Generated canonical wire types into `frontend/src/api/generated.ts` from OpenAPI. Added explicit wire-to-view mapping in `normalize.ts` for IDs, candidate status, source proposal/provenance, health reasons, selection scores/reasons, paired attempts/enforcement/checks/raw responses, memory versions and audit events.
- Updated the real HTTP client to use those DTOs, send the required approval reason, and reuse an idempotency key for retries of the same decision within the page session. Removed the provisional-field assumption from the docs.
- Added the exact exception-reference editor field and preserve it during stage/revision. Added preference scope support. Require the displayed completed run to be the candidate's latest eligible run before enabling approval. Align retest/revision buttons with backend lifecycle states.
- Fixed initial URL hydration so reload cannot erase candidate/run IDs before restoration. Reject a URL combining different candidates/runs. Poll without overlapping requests and stop at terminal status. Expose stored raw model responses and all selection reasons.
- Enable explicit optional speech requests when the backend is configured-but-unverified (degraded), so its first generation can be attempted; disabled/unavailable voice stays disabled. Errors remain independent of review.
- Committed frontend dependency lockfile and generation/build/test scripts. Upgraded Vite to 7.3.8, within the existing React plugin's supported range, resolving the two findings in the original install. Node 20.19+ or 22.12+ is required; verification used Node 24.
- Added six Playwright checks, including the synthetic fixture-driven review/approval/reload flow, stale evidence, polling, unavailable backend, explicit synthetic mode and a real Vite→FastAPI health request. Tests start local servers with the paid-work worker disabled.
- Root README now starts the integrated v1 API/React app and uses PowerShell instructions. The previous README is preserved in `docs/legacy-mvp.md`. Dockerfile/Procfile remain legacy-only. Updated frontend setup/demo notes and added `docs/demo-runbook.md`.

### Verified on the merged checkout

| Check | Result |
| --- | --- |
| Python backend + preserved MVP tests | 60 passed, 2 credential-dependent skips |
| Frontend lockfile clean install | `npm ci --ignore-scripts --offline` passed from the local package cache |
| Canonical TypeScript generation | Passed |
| TypeScript + production build | Passed, Vite 7.3.8 |
| Playwright (installed Chrome, headless) | 6 passed; desktop/mobile screenshots inspected |
| Real local API/proxy | FastAPI health through Vite passed; worker disabled |
| npm dependency audit | 0 vulnerabilities reported after the compatible update |
| Whitespace check | Passed |

Browser review payloads are explicitly synthetic test fixtures, not real model evidence. Screenshots under ignored `artifacts/` are test artifacts. Real application Atlas writes, actual extraction/agent runs/search, paid TTS and restart persistence still require local credentials; no connected success is claimed. The earlier plugin read-only connection remains a separate observation.

### Next branch split

Both agents must fetch the resulting `origin/main` and start their next independent branches from the same shared HEAD. Keep backend ownership with Agent A and frontend ownership with Agent B. Previous feature branches remain intact as history. Do not base follow-up work on an old pre-integration feature tip; the wire adapters and integration fixes are on main.

## 2026-11-14 — Pre-merge handoff checkpoint

**Historical state at that checkpoint:** backend was committed and pushed; frontend readiness was pending. The integration entry above supersedes this waiting state.

| Reference | Commit | Purpose |
| --- | --- | --- |
| Shared `main` baseline | `2f06521` | Preserves the remote legacy MVP and publishes the two-agent plan |
| Backend foundation | `d934118` | New v1 API, DTOs/OpenAPI, Atlas persistence, provider/runner/review, optional TTS |
| Tested backend | `0029fc7` | Reliability fixes, dependency pins, tests, setup/smoke/status documentation |
| Observed frontend handoff candidate | `f061fe8` | React/Vite review UI on `feat/membrane-review-ui`; not yet merged or validated by Agent A |
| This handoff entry | See commit containing this entry | Adds validated contract examples, merge checklist, and updated coordination instructions |

### Backend change map

| Area | Files / directory | What the frontend agent needs to know |
| --- | --- | --- |
| HTTP interface | `contracts/openapi.yaml`, `contracts/README.md` | Interface authority; snake_case, string IDs, exact enum values, consistent errors |
| Synthetic examples | `contracts/examples.json` | Schema-validated documentation examples, visibly synthetic; never present as live evidence |
| API implementation | `backend/app/main.py`, `models.py` | Use `backend.app.main:app` on port 8000; the earlier `membrane.app:app` has a different contract |
| Policy/evaluation | `backend/app/policy.py`, `selection.py`, `runner.py` | 12 cases × 2 sides × 2 repetitions; show attempts separately from enforcement |
| Lifecycle/persistence | `backend/app/service.py`, `store.py` | Staging/revision never activate memory; approval needs exact passing evidence and idempotency key |
| Providers | `backend/app/provider.py`, `voice.py` | Server-only keys; optional exact-answer speech cannot change admission |
| Setup | `.env.example`, `backend/requirements*.txt`, `scripts/backend_setup.py` | V1 config differs from preserved legacy `LLM_*` config; secrets stay local |
| Synthetic source | `fixtures/support-4821.png` | Upload through the real screenshot endpoint; do not pretend it is actual customer data |
| Verification | `backend/tests/`, `scripts/backend_smoke.py` | Unit/API tests use explicit doubles; live smoke requires real credentials and is billable |

### Known differences and integration risks

- Both implementations remain in the repo: legacy Python/static demo and new v1 API/React review flow. Existing Dockerfile/Procfile and root README still describe the legacy entrypoint. Do not treat those deployment files as verified v1 launch configuration. The original scope is local-only; frontend README and backend setup docs must point at the same v1 API.
- Existing Atlas collections and Voyage auto-embedding index are preserved. V1 setup uses a workspace namespace and its own explicit-embedding Search index. A working plugin session does not replace `MONGODB_URI` for Python.
- Backend changed root `.env.example` and `.gitignore`; frontend owns its dependency manifest, lockfile, UI README and source. Compare those ownership boundaries before merging.
- The observed frontend commit has no committed lockfile or browser smoke tests in its file list. Confirm its install/build/typecheck/test status with the teammate rather than marking those done.
- Generated OpenAPI must match the Pydantic DTOs. Regenerate after intentional API changes; have the frontend regenerate or align its types. Examples can be regenerated using `python -m scripts.export_contract_examples` without external calls.
- No live application credentials have been provided. Real extraction/model runs, application Atlas writes/search, paid TTS, and restart acceptance are unverified. M5 benchmark execution remains deferred.

### Latest verified checks

Backend plus existing deterministic MVP tests: **60 passed, 2 skipped** on November 14. Credential-dependent checks were skipped. OpenAPI regeneration, compilation and whitespace checks passed. Missing-credential preflight returned unavailable statuses and a nonzero exit as expected. The frontend branch is observed only; no frontend build/browser success is claimed here.

Next owner: teammate confirms frontend readiness, then integrator follows `merge-checklist.md`. Do not start either agent's next feature branch before the shared integration commit is identified.
