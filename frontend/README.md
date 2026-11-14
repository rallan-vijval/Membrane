# Membrane review UI

React + TypeScript + Vite. One screen: source and candidate on the left, the A/B behavior
preview in the middle, the reviewer decision on the right, history in the footer.

The browser only calls `/api`. Vite proxies that to the backend at `http://127.0.0.1:8000`.
No keys or connection strings live in the frontend.

## Run (PowerShell)

```powershell
cd frontend
npm install
npm run dev          # http://127.0.0.1:5173
```

Start the backend first (see the root README). Other commands:

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

`src/api/types.ts` and `src/api/http.ts` were written from `docs/two-agent-plan.md` before
`contracts/openapi.yaml` existed. When the backend publishes the contract:

1. Regenerate or correct `src/api/types.ts` from it.
2. Fix any drift in `src/api/http.ts` (paths, request bodies) and `src/api/synthetic.ts`.
3. Run `npm run typecheck`.

Assumptions most likely to need changing: field names inside `Run.cases[].executions[]`
(`outcome`, `attempt`, `enforcement`), `Run.progress`, `Run.selection[]`, the `Scope` shape,
and the body of `POST /api/candidates/{id}/approve` (`{ run_id }`).

## Behavior notes

- A run is polled every two seconds and polling stops at `completed`, `failed` or
  `inconclusive`, or when the page is left.
- The selected candidate and run IDs are kept in the URL, so a reload restores the view from
  the backend.
- Approve is enabled only when the backend reports the candidate as `eligible` and the shown
  run's admission as `eligible`. A 409 asks the reviewer to retest.
- Reviewer actions (approve, quarantine, revise) send an `Idempotency-Key` header.
- "Listen to this answer" appears only when the backend reports voice as `ready`. An audio
  failure shows a message and never blocks review.
- Status is always icon plus word, never color alone. All controls are keyboard-operable.

## Three-minute demo runbook

1. **(0:00) The problem.** "One manager approves one exception. The agent remembers a rule for
   every VIP." Upload the synthetic screenshot. Point at the quotation and the *untrusted source*
   label.
2. **(0:30) Stage the broad memory.** Keep the proposed text ("All VIP customers can keep
   refunded items"), scope Global, **Stage candidate**. Point at the header: active memory has
   not changed.
3. **(0:45) Run behavior test.** While it runs, open *Why these cases*: sentinels always run,
   Vector Search picked the related ones. When it finishes, the red rows show
   "Refund, return waived". Expand one: same task on both sides, `waive_return` flipped, the tool
   guard blocked it, and it still counts as a regression.
4. **(1:30) Quarantine or narrow.** The decision panel says quarantine and Approve is locked.
   Edit the text to the order 4821 exception, scope One order / 4821, **Save as revision**.
5. **(1:50) Retest.** Only order 4821 changes, shown in green as an intended safe change.
   Every other case is unchanged.
6. **(2:20) Approve and activate.** The header's active version advances. Open the footer:
   version lineage, reviewer events, run ID, model and usage.
7. **(2:45) Reload the page.** Everything comes back from Atlas.

If the model does not reproduce the broad-rule regression live, say so and show the stored run.
Do not present synthetic mode as a result.
