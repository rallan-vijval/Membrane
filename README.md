# Membrane

**Preview what a new memory will make your agent do.**

Upload a synthetic support screenshot, stage a candidate memory, compare isolated baseline/candidate agent behavior, review exact attempted refund arguments and trusted policy checks, then quarantine or approve an exact passing revision. Staging never activates memory. All refunds are simulated.

The integrated review app uses **FastAPI (`backend.app.main:app`) + React/TypeScript/Vite (`frontend/`)**. Its contract is in [`contracts/openapi.yaml`](contracts/openapi.yaml), with a [frontend integration guide](contracts/README.md). The earlier `membrane/` Python/static demo remains intact; its separate instructions are preserved in [legacy-mvp.md](docs/legacy-mvp.md). Do not mix their API entrypoints or environment variable names.

## Run locally — PowerShell

From the repository root, with Python 3.11+ and Node 20.19+ or 22.12+ (Node 24 was used for verification):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
# First setup only; preserve an existing .env:
Copy-Item .env.example .env
```

Edit local `.env`: fill `MONGODB_URI`, `OPENAI_API_KEY`, `AGENT_MODEL` and `VISION_MODEL`. The Atlas plugin does not supply the Python app's database credentials or an OpenAI API key. `MONGODB_DB=membrane`; the v1 app uses its own workspace namespace. Optional ElevenLabs settings remain disabled by default. Never put secrets in frontend variables or Git.

Initialize the existing Atlas sandbox without deleting unrelated data:

```powershell
.\.venv\Scripts\python.exe -m scripts.backend_setup seed
.\.venv\Scripts\python.exe -m scripts.backend_setup seed --with-embeddings
.\.venv\Scripts\python.exe -m scripts.backend_setup index
.\.venv\Scripts\python.exe -m scripts.backend_setup preflight
```

Embedding setup and provider preflight make billable API requests. See [backend setup](docs/backend-setup.md) for budgets, failure states and optional speech, and [Atlas setup](docs/atlas-setup.md) for index JSON/UI fallback. No public deployment or tier changes are required.

Terminal 1:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Terminal 2:

```powershell
cd frontend
npm ci
npm run dev
```

Open [the review UI](http://127.0.0.1:5173). API documentation: [local Swagger UI](http://127.0.0.1:8000/docs). Without credentials, the backend still starts and reports unavailable integrations accurately. For an explicitly labeled UI-only rehearsal, open [synthetic mode](http://127.0.0.1:5173/?synthetic=1); it makes no model/Atlas calls and is not evidence.

## Verify

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests tests -q
cd frontend
npm run generate:api
npm run build
npx playwright install chromium
$env:MEMBRANE_TEST_PYTHON = (Resolve-Path ..\.venv\Scripts\python.exe).Path
npm test
```

Browser tests start the frontend and backend locally with the run worker disabled. Review-flow HTTP responses are explicitly synthetic fixtures; a separate test reaches the actual FastAPI health endpoint through the Vite proxy. Browser tests verify paired evidence, approval errors, polling, reload, mobile layout, and synthetic opt-in. They do not establish real provider/Atlas acceptance. To use installed Chrome instead of downloaded Chromium, set `$env:PLAYWRIGHT_CHANNEL='chrome'`.

For billable connected acceptance after preflight, run `python -m scripts.backend_smoke` from the configured virtual environment. It stops at eligibility; `--approve` intentionally tests activation. Never fabricate a broad-memory regression if the chosen model resists it.

## Team handoff

Read [the change log](docs/CHANGELOG.md), [two-agent ownership plan](docs/two-agent-plan.md), and [merge checklist](docs/merge-checklist.md). Future work branches from the verified shared `main` checkpoint, with backend and frontend ownership kept separate. Credentials, real provider runs/search/TTS, and the held-out benchmark remain explicit acceptance items until actually verified. Existing Dockerfile/Procfile target the legacy demo and have not been migrated to this local review app.
