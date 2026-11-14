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
