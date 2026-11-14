# Team change log

Read this first when joining the project. Dates use America/New_York. Append an entry for each handoff, contract change, integration fix, or merge; include branch, commit, verification, and any action needed by the other agent. Never include secrets or claim mock results are live.

## 2026-11-14 — Pre-merge handoff checkpoint

**State:** backend is committed and pushed; frontend branch has appeared, but its readiness handoff is pending. Do not merge or begin a new branch split yet. Wait for the teammate, integrate both branches into `main`, verify together, then branch again from that shared merge commit.

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
