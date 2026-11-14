# Agent B progress (frontend and demo)

Branch: `feat/governed-memory-ui`, created from shared baseline `3b456a4`. Owner files only:
`frontend/`, this file. No backend, contract or root configuration was edited.

## 2026-11-14, checkpoint 1: fixes and intake on top of the integrated UI

Kept the integrated API layer (`generated.ts`, `normalize.ts`, `http.ts`, `synthetic.ts`, view types) and
the existing labels the Playwright tests rely on. Changes:

- **Bug fix, real flow:** after a run finished, Approve could stay disabled. The final poll set the
  terminal run before reading the candidate; that ended the polling effect and the candidate's new
  state was dropped. The mocked tests did not catch it because their candidate becomes eligible when
  the run is created. `App.tsx` now reads the candidate first on the final poll.
- **Source intake:** images in other formats, PDFs (page 1), text files and video (one chosen frame)
  are converted in the browser to the PNG/JPEG the API accepts, with a visible note. Word and Office
  files are refused with an instruction to export a PDF. `src/intake.ts`; pdf.js vendored under
  `public/vendor/pdfjs/`, no dependency or lockfile change.
- **Evidence table:** cases sorted with violations first; a membrane column between A and B; the exact
  changed tool arguments shown as chips in the B cell; a per-classification tally in the decision panel.
- **Footer:** lists the memory in force.
- **Styles:** full restyle; mobile layout stacks the table and passes the no-horizontal-scroll check.
- **Test file:** one label string updated (`Source file (image, PDF, text or video; synthetic data only)`).

### Verification, stated exactly

- Bundled with esbuild and driven in headless Chrome in synthetic mode: text and PDF conversion, PNG
  upload, stage, broad run quarantined, case detail, revision, narrow run eligible, Approve enabled and
  clicked, 390 px width without horizontal scroll, no page errors.
- Type-checked with stand-in React typings only.
- **Not run:** `npm ci`, `npm run build` (Vite), `npm test` (the six Playwright checks). Package
  installs are blocked in the authoring environment. Run all three before merging.
- **Not exercised:** video frame capture; anything against the real backend.

### Not started (waiting on Agent A's contract checkpoint)

Lifetime (TTL) picker, governed-memory panel with expiry and revoke, per-case retrieval evidence,
"Run with active memory" panel, trace links, updated runbook and root README.

### Open point for the integrator

Branch `feat/membrane-review-ui` has three commits after the merged `f061fe8` (a redesign written
against wire-shaped types). They are superseded by this branch and should not be merged.

## 2026-11-14, checkpoint 2 withdrawn

The support-inbox view (commit `49c66a5`) was removed at the owner's request by revert `b4579e3`. Nothing
from it remains in the tree.

## 2026-11-14, checkpoint 3: Task B from `docs/NEXT_PHASE_PLAN.md`

Built against Agent A's published contract (`contracts/openapi.yaml` at `a025e71`, branch
`feat/governed-memory-backend`). Files: `frontend/src/governed.tsx` (new), `api/governedWire.ts` (new),
`api/types.ts`, `normalize.ts`, `http.ts`, `synthetic.ts`, `components.tsx`, `App.tsx`, `styles.css`,
`tests/review.spec.ts`.

| Plan item | State |
| --- | --- |
| Lifetime on stage/revise (1 to 1440 min, default 60, sent as `ttl_seconds`, preserved across revisions) | Done |
| Order scope needs both order and customer ID before staging | Done (button stays disabled) |
| Governed-memory panel: IDs, scope, expiry, availability, lineage; backend `availability` is the authority | Done |
| Refresh after approve/revoke and when an expiry boundary passes | Done (timer only schedules a re-read) |
| Revoke per active entry: required reason, explicit `base_version_id`, stable idempotency key, 409 shown then refreshed | Done |
| Run details: memory retrieval per case, separate from test-case selection, candidate overlay marked "B only" | Done |
| Old runs: "Retrieval provenance unavailable", nothing inferred | Done |
| "Run with active memory": fixture picker, bounded execute, result/retrieval/guard/version, reload by `?execution=` | Done |
| New health components (embeddings, memory search, vision, tracing) shown when reported | Done |
| Trace links only when the backend supplies them | Done (run and execution) |
| ElevenLabs playback | Unchanged from baseline |
| Synthetic fixtures extended, banner unchanged, no fallback from real mode | Done |
| Regenerate `generated.ts` from the new contract | **Not done.** `openapi-typescript` could not be run here. `governedWire.ts` holds hand-written wire types for the new shapes; after merging A's contract run `npm run generate:api` and swap them in. |
| New Playwright tests for TTL/revoke/retrieval/live task | **Not done.** Existing tests adjusted only: scope select located by label (there are now two selects), and the mock answers the two new GET endpoints. |
| Root README and demo runbook | Runbook section added; root README untouched (Agent A's entry points are still changing) |

New-endpoint failures (for example a backend without `/api/memory/entries`) are shown inside their own panel
and never raise the page-level alert, so the base review flow keeps working against an older backend.

### Verification, stated exactly

Headless Chrome, synthetic mode, esbuild bundle: order 4821 run before approval (asks for return); broad
rule quarantined with retrieval evidence visible; revision blocked until customer ID entered; 1-minute
lifetime approved; order 4821 run again (refund, return waived, guard allowed); another VIP unchanged;
entry shown as expired after its minute and order 4821 back to asking for the return; a memory revoked with
a reason and a revoke event listed; 390 px width fits; no page errors. Type-checked with stand-in React
typings.

**Not run:** `npm ci`, `npm run build`, `npm test`, `npm run generate:api`, and anything against the real
backend. The field mapping in `governedWire.ts` follows the contract text but has not met a live response.
