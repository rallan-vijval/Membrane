# Membrane review UI

React + TypeScript + Vite. One screen: source and candidate on the left, the A/B behavior
preview in the middle, the reviewer decision on the right, history in the footer.

The browser only calls `/api`. Vite proxies that to the backend at `http://127.0.0.1:8000`.
No keys or connection strings live in the frontend.

## Run (PowerShell)

```powershell
cd frontend
npm ci
npm run dev          # http://127.0.0.1:5173
```

Start the v1 backend first with `python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000` from the configured backend environment (see the root README). The preserved `membrane.app:app` entrypoint uses a different contract. Node 20.19+ or 22.12+ is required by the patched Vite 7 toolchain; integration was verified on Node 24. Other commands:

```powershell
npm run typecheck    # tsc --noEmit
npm run build        # typecheck + production build into dist/
```

## Real mode and synthetic mode

- **Real mode (default).** Every panel shows what the backend returns. If the API is down or an
  integration is unavailable, the UI shows the error and the health pills say so. It never
  substitutes made-up results.
- **Synthetic mode (opt-in).** Open `http://127.0.0.1:5173/?synthetic=1`, or set
  `VITE_SYNTHETIC=1`. An in-browser stand-in replays a scripted flow so the UI can be built and
  rehearsed without the backend. A banner stays on screen the whole time, health pills read
  `disabled`, and the run is tagged `synthetic`. Nothing in this mode is evidence.

## Contract status

`src/api/generated.ts` is generated from the canonical `contracts/openapi.yaml` with `npm run generate:api`. `src/api/normalize.ts` explicitly maps wire DTOs into the presentation models in `types.ts`; synthetic mode uses those same view models. The HTTP adapter sends exact request bodies, including the approval reason, and reuses idempotency keys for repeated identical decisions within the page session.

After a contract change, regenerate wire types, update the typed adapters, run `npm run build`, and run the browser tests. Scope preserves the exact order, customer and exception reference. Raw responses and policy judgments remain visible beside attempted arguments.

```powershell
npx playwright install chromium
$env:MEMBRANE_TEST_PYTHON = (Resolve-Path ..\.venv\Scripts\python.exe).Path
npm test
# Optional alternative using installed Chrome:
# $env:PLAYWRIGHT_CHANNEL='chrome'
```

Tests start local Vite and FastAPI servers, disable the paid-work worker, and use explicitly synthetic HTTP fixtures for the review workflow. An additional unmocked health request verifies the actual proxy/backend connection. They do not establish live Atlas/model/TTS success. Ports 5173 and 8000 must be free.

## Behavior notes

- A run is polled every two seconds and polling stops at `completed`, `failed` or
  `inconclusive`, or when the page is left.
- The selected candidate and run IDs are kept in the URL, so a reload restores the view from
  the backend.
- Approve is enabled only when the backend reports the candidate as `eligible` and the shown
  run's admission as `eligible`. A 409 asks the reviewer to retest.
- Reviewer decisions (approve and quarantine) send an `Idempotency-Key` header. Revision creates a new candidate.
- "Listen to this answer" appears when voice is `ready` or configured-but-unverified (`degraded`). An audio
  failure shows a message and never blocks review.
- Status is always icon plus word, never color alone. All controls are keyboard-operable.

## Three-minute demo runbook

1. **(0:00) The problem.** "One manager approves one exception. The agent remembers a rule for
   every VIP." Upload the synthetic screenshot. Point at the quotation and the *untrusted source*
   label.
2. **(0:30) Stage the broad memory.** Explicitly edit the candidate to "All VIP customers can keep
   refunded items", scope Global, **Stage candidate**. Do not claim extraction always proposes that rule. Point at the header: active memory has
   not changed.
3. **(0:45) Run behavior test.** While it runs, open *Why these cases*: sentinels always run,
   Vector Search picked the related ones. Report the observed result. If there are new unsafe attempts, expand one to show exact `waive_return` arguments and guard rejection. A blocked attempt still counts as a regression; a resistant model must not be presented as a failure.
4. **(1:30) Quarantine or narrow.** The decision panel says quarantine and Approve is locked.
   Edit the text to the order 4821 exception, scope One order / 4821, customer `customer-4821`, exception reference `exc-4821`, **Save as revision**. The trusted exception lives on the server; typing a reference cannot create authority.
5. **(1:50) Retest.** Only order 4821 changes, shown in green as an intended safe change.
   Every other case is unchanged.
6. **(2:20) Approve and activate.** The header's active version advances. Open the footer:
   version lineage, reviewer events, run ID, model and usage.
7. **(2:45) Reload the page.** Everything comes back from Atlas.

If the model does not reproduce the broad-rule regression live, say so. Do not present synthetic mode as a result. Synthetic mode stores rehearsal state only in browser memory; it does not survive reload. The reload-persistence claim applies to the connected Atlas flow; the browser contract test exercises reload using explicit HTTP fixtures.
