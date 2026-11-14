# Agent A: review API backend

The teammate owns the new React frontend. This backend lives on `feat/membrane-backend`. Existing `membrane/` code and its static UI are preserved; the new frontend must use the **v1** entrypoint below, not `membrane.app:app`.

## PowerShell startup

Run from the repository root (the backend worktree is also a repository root):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
Copy-Item .env.example .env
# Edit .env locally. Never commit or paste credentials into chat.
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Do not overwrite an existing `.env`. On first setup, fill `MONGODB_URI`, `OPENAI_API_KEY`, `AGENT_MODEL`, and `VISION_MODEL`. The OpenAI key must be an API project key with usable billing/quota, not a MongoDB or ElevenLabs key. One OpenAI key covers agent decisions, screenshot extraction and embeddings. The Atlas plugin's session handle cannot authenticate the Python app.

`MONGODB_DB=membrane` and `WORKSPACE_ID=membrane-demo-v1` isolate this implementation's records. `.env.example` also retains the earlier MVP's `LLM_*`/`DB_NAME` options; those apply only to its legacy entrypoint. The v1 backend uses `OPENAI_API_KEY`, `AGENT_MODEL`, `VISION_MODEL`, and `MONGODB_DB`.

Without secrets, the server still starts, `/docs` and `/openapi.json` work, and `/api/health` reports unavailable database/model and disabled voice. It does not silently install a fake database/provider. Most data routes require seeding.

## Non-destructive initial setup

```powershell
.\.venv\Scripts\python.exe -m scripts.backend_setup seed
# The next command makes billable embedding requests (36 task descriptions initially).
.\.venv\Scripts\python.exe -m scripts.backend_setup seed --with-embeddings
.\.venv\Scripts\python.exe -m scripts.backend_setup index
# Billable: model access checks, one vision extraction, one structured decision,
# one embedding request, plus a real Atlas known-neighbor search.
.\.venv\Scripts\python.exe -m scripts.backend_setup preflight
```

The seed uses deterministic workspace-scoped IDs/upserts and never deletes existing data. Existing legacy records/indexes stay intact. Search setup has a bounded 90-second readiness wait; see `atlas-setup.md` if creating Search indexes programmatically is unauthorized. Preflight exits nonzero if any database/model/search check fails and prints redacted status. It does not provision or upgrade cloud resources.

The bundled `fixtures/support-4821.png` is a synthetic screenshot. The UI uploads it through the same real extraction endpoint as any other accepted image. Candidate examples are in `backend/app/fixtures.py`; the editable broad example is intentional, not a claim about the extractor's output.

## API, run budget and worker

Read `contracts/README.md` and `contracts/openapi.yaml`. Generate frontend types from that contract. The server serves uploaded images and optional generated audio. Lists are bounded at 100; 12 cases have 4 executions each, stored separately from summaries. JSON summaries are computed from stored results through MongoDB aggregation.

The runner uses one structured model decision per execution (at most one simulated refund attempt), within the original three-turn upper bound. It makes 48 initial requests for a complete admission suite, alternates side order, and retries only transient errors once. Each attempted execution request, including retries, atomically consumes `MAX_RUN_MODEL_CALLS` (default 80). Exhausted budgets yield inconclusive evidence, never approval. Provider SDK automatic retries are disabled. Setup/extraction/embedding usage is separate from the admission execution counter. No currency estimates are invented.

For a live backend smoke after preflight, run `python -m scripts.backend_smoke`. This is billable (two admission suites plus screenshot extraction and selection embeddings), persists its evidence, and stops at eligibility. Add `--approve` only when intentionally exercising reviewer activation. It reports actual model outcomes, including a broad rule being resisted. Browser automation remains the frontend agent's responsibility.

The original three-turn worst-case estimate is 144 before retries. This implementation's single-turn runner needs at most 96 execution requests with every request retried once; the 80 cap can intentionally stop an unlucky run. Set a reviewed cap locally. Configured concurrency is at most two provider requests; there is one leased run worker. Freeze includes prompt, tool schema, tasks, memory, candidate, exceptions, and provider config. Changed config/prompt after restart makes resumed cases inconclusive.

Use a single Uvicorn process; do not add `--workers`. For intentional API-only operation set `WORKER_ENABLED=false` (queued work then waits for a worker-enabled instance). Runs lease for at least three model timeouts plus 30 seconds. Per-case persistence checkpoints avoid rerunning completed cases after restart. Interrupted suite preparation becomes visibly inconclusive after its bounded preparation window.

Approval uses an authoritative atomic workspace pointer with a pending decision receipt; the next worker/read/decision reconciles interrupted candidate/audit updates. Prepared but unreferenced versions are excluded from history. There is no force-approval path. History is append-only by application convention, not tamper-proof.

## Optional ElevenLabs

Fill `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, and model settings, then set `VOICE_ENABLED=true`. Verify your promotional credits cover API TTS and set an account key quota. The backend does not claim credit eligibility or assume dollar conversion. Voice health stays degraded until generation is attempted; it is independent of the safety verdict.

Only exact stored answers are synthesized, on explicit request. Both sides use identical voice/model/settings. Cache identity includes text/workspace/model/voice/settings. Default request length is 2,000 characters and workspace lifetime budget is 20,000 characters; configure account limits too. Generation attempts consume local quota even if the provider fails. Failed/in-progress cached requests are visible errors, not automatically retried paid calls. Audio is a presentation artifact, not a new agent execution or approval mechanism.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q
.\.venv\Scripts\python.exe -m scripts.export_contract
git diff --check
```

Test database/provider doubles exist only under `backend/tests`; the real app cannot select them through configuration. The tests exercise the broad→quarantine→scoped revision→approval workflow, frozen inputs, guard-denied attempts, failures/budgets, selection boundaries, concurrency, crash receipts and worker resume. The frontend agent owns browser smoke and UI build verification. Application-level live extraction, provider execution, Atlas writes, real Vector Search, restart persistence, and ElevenLabs generation require credentials and have not yet passed connected acceptance. The optional held-out benchmark (M5) is deferred until that live core is verified.
