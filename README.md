# Membrane

**See what a new memory will make your agent do, before it does it.**

Built on November 14, 2026 at *Agents in Context Toronto: a MongoDB Hackathon*, for problem statement 2,
**Memory You Can Govern**.

## The problem

A support agent learns from what it reads, and sometimes it learns the wrong lesson. A supervisor approves
one exception: "order 4821 may be refunded without a return." The agent remembers "all VIP customers can
keep refunded items." Nothing in that sentence looks malicious, so a content filter passes it, and the agent
starts waiving returns for every VIP.

## What Membrane does

A new memory is tested before the agent may keep it.

1. **Stage.** A source (the supervisor's note) is uploaded and a candidate memory is proposed from it. The
   candidate is stored apart from active memory; the live agent cannot see it.
2. **Replay.** Twelve synthetic support requests are run in fresh sessions, twice with current memory and
   twice with the candidate added: 12 decisions across 3 selected requests, with two calls running concurrently.
3. **Compare actions.** Every refund the agent tried is checked against fixed policy. The review screen
   shows the exact tool arguments that changed, for example `waive_return: false → true`.
4. **Decide.** A candidate that breaks policy is quarantined. A reviewer can narrow it to order 4821 and
   test again. Only an exact passing run can be approved, and approval creates a new memory version.
5. **Govern.** An approved memory has a scope and a lifetime. It expires on its own, can be revoked with a
   reason, and every decision is on record.

All customers, orders and refunds are synthetic. The refund tool only records what the agent attempted.

## How it answers the track's questions

| Question | In this project |
| --- | --- |
| How do you keep one client's memory from leaking into another's? | Each memory carries a workspace and a scope (global, one order and customer, or one customer's preference). Retrieval filters on them and rechecks every returned memory against the live record. |
| How does the agent fix or drop a memory that is wrong or expired? | A revision is a new candidate that must pass its own test. Each memory has a lifetime (`ttl_seconds`); expired memories stop being retrieved. Revoke creates a new version without the entry. Nothing is deleted from history. |
| How do you prove a memory changed behavior and didn't just fill the prompt? | The same request runs with and without the memory in isolated sessions and the recorded tool calls differ. "Run with active memory" shows the live agent's action before approval, after approval, and after expiry or revoke. |

## What is in the app

**Review screen (React)**

- **Source and candidate.** Upload an image, PDF (page 1), text file or a video frame; the browser converts
  it to the PNG or JPEG the API accepts and says so. Edit the proposed memory, its scope and its lifetime.
- **Behavior preview.** Current memory (A) beside the candidate (B) for each request, violations first, with
  the changed arguments, the tool guard's verdict, the raw model response, and which memories the agent was
  given for that case.
- **Decision.** Approve unlocks only when the backend reports a passing run for that exact candidate.
- **Memory in force.** Every active memory with scope, expiry and a Revoke control.
- **Run with active memory.** Hand one request to the live agent and see what it does with the memory in
  force.
- **Record.** Versions, reviewer decisions and run details.

**Backend (FastAPI)**

- Screenshot extraction, candidate staging and revision, test selection, the paired runner, deterministic
  refund policy, admission (eligible, quarantine, inconclusive), approval, expiry, revocation and audit.
- **MongoDB Atlas** stores memory versions and entries, sources, fixtures, every run result and every
  reviewer event. **Atlas Vector Search** picks the related test requests and retrieves the agent's memory.
- **DeepSeek** is the agent model and reads the uploaded image. **Voyage AI** makes the embeddings.
- Optional and off by default: **ElevenLabs** reads a stored agent reply aloud; **LangSmith** tracing.

The HTTP contract is [`contracts/openapi.yaml`](contracts/openapi.yaml); see the
[frontend integration guide](contracts/README.md).

## Run locally

Needs Python 3.11+ and Node 20.19+ or 22.12+. Commands are for macOS or Linux; on Windows PowerShell use
`.\.venv\Scripts\python.exe` in place of `python` and `Copy-Item` in place of `cp`.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements-dev.txt
cp .env.example .env          # first setup only; do not overwrite an existing .env
```

Fill in `.env`: `MONGODB_URI` (the hackathon Atlas Sandbox), `DEEPSEEK_API_KEY` and `VOYAGE_API_KEY`. Leave
voice and tracing off for the first run. Keys stay in this file: never in the frontend and never in Git.

Set up Atlas once. These commands do not delete existing data; the embedding and preflight steps make
billable API calls.

```bash
python -m scripts.provider_preflight
python -m scripts.backend_setup seed --with-embeddings
python -m scripts.backend_setup index
python -m scripts.backend_setup preflight
```

Terminal 1, the API:

```bash
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Terminal 2, the review screen:

```bash
cd frontend
npm ci
npm run dev
```

Open <http://127.0.0.1:5173>. The lights in the header show which integrations are ready. API docs are at
<http://127.0.0.1:8000/docs>. More detail: [backend setup](docs/backend-setup.md),
[provider setup](docs/integrations-setup.md), [Atlas setup](docs/atlas-setup.md).

### Without keys: synthetic mode

Open <http://127.0.0.1:5173/?synthetic=1>. The page runs on labelled stand-in data in the browser, with a
banner that stays on screen. No model runs and Atlas is not contacted, so nothing shown there is evidence.
Real mode never switches to it by itself.

`frontend/render.yaml` is a Render blueprint for a static copy of that synthetic demo. It does not deploy
the backend.

## Demo flow

Use the bundled synthetic note, `fixtures/support-4821.png`.

1. In **Run with active memory**, run the order 4821 request. The agent asks for the return.
2. Upload the note. Stage "All VIP customers can keep refunded items." with scope Global and run the
   behavior test. The VIP cases turn red and the candidate is quarantined.
3. Revise to order 4821 with customer `customer-4821` and exception `exc-4821`, pick a short lifetime, and
   test again. Only order 4821 changes. Approve it.
4. Run the order 4821 request again: refund without return, allowed by the tool guard. Run another VIP's
   request: unchanged.
5. Let the lifetime run out, or revoke the memory with a reason. Order 4821 goes back to asking for the
   return.

Report what the model actually does. If it resists the broad memory, say so. The full script is in the
[demo runbook](docs/demo-runbook.md).

## Verify

```bash
python -m pytest backend/tests tests -q
cd frontend
npm run generate:api
npm run build
npm test                      # set PLAYWRIGHT_CHANNEL=chrome to use installed Chrome
```

The browser tests start the frontend and the backend locally with the run worker switched off. Their review
and governance responses are synthetic fixtures; one test reaches the real FastAPI health route.

## Status

Checked on the integrated `main` on November 14, as recorded in
[integration-fix-log.md](docs/integration-fix-log.md):

| Check | Result |
| --- | --- |
| Backend tests | 96 passed, 2 live checks skipped |
| TypeScript and production build | Passed |
| Browser tests | 14 passed |

**Not yet verified:** a full run against live services. Screenshot extraction, real model runs, Vector
Search through the application, expiry and revoke on real data, voice and tracing all still need a run with
real credentials. The tests above use stand-ins for the model, the embeddings and Atlas.

## Repository layout

```
backend/app/       FastAPI service: runner, policy, memory governance, providers, voice
backend/tests/     backend tests
contracts/         OpenAPI contract, examples, frontend integration guide
frontend/          React + TypeScript + Vite review screen and its browser tests
fixtures/          the synthetic supervisor note
scripts/           Atlas setup, preflight, smoke test, contract export
docs/              setup guides, plans, progress logs, change log
membrane/          the first prototype from the morning, kept for reference (docs/legacy-mvp.md)
```

The root `Dockerfile` and `Procfile` belong to that first prototype and do not run the current app.

## How it was built

Everything in this repository was written during the hackathon on November 14, 2026 by the team, working
with AI coding agents, including Claude and Codex. Work was split by ownership so the agents never edited the
same files: backend and contract, frontend and demo, provider integrations. The plans, each agent's progress
log and the integration reviews are in `docs/`:
[change log](docs/CHANGELOG.md), [next-phase plan](docs/NEXT_PHASE_PLAN.md),
[backend progress](docs/agent-a-progress.md), [frontend progress](docs/agent-b-progress.md),
[integration review](docs/integration-review.md).

## Limits

- A passing test is evidence for the selected cases, not a guarantee. Scope, lifetime and revoke exist
  because a bad memory can still pass.
- Expected outcomes come from fixed policy code, never from the model grading itself.
- A PDF contributes its first page and a video one chosen frame.
