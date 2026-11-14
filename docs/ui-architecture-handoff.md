# Two-page UI architecture

Implemented on feat/memory-experiments-voice-sources. This is page structure and functional data visualization; the existing palette is retained so the visual team can reskin it independently.

## Upload and test

The default page shows upload/voice recording first. Proposal fields appear after a source is available. Then the user saves the proposal, runs the existing admission test, sees a compact decision-progress ring, and approves or rejects after the run reaches a terminal state. The detailed case tables, source/version metadata, service status, history, scope experiments and memory management are not spread across the simple screen. Source/version metadata remains in a disclosure when needed. Recording is cancelled and microphone tracks released when leaving this page.

The Open detailed results button opens the selected run on the Dashboard. Navigation never starts or repeats a paid test. The original server eligibility gate remains the authority for approval.

## Dashboard

Four detail sections: Overview, Test evidence, Scope experiments, Approved memory. Selection and navigation preserve current proposal/run state and URL parameters. Browser back/reload restore the workspace; legacy execution links open Dashboard/Approved memory.

Overview provides:

- Outcome bars from the selected admission run. Click to filter the decision matrix.
- A request-by-decision matrix (without/with memory, two repetitions). Cells distinguish passed checks, failed checks, invalid responses and pending evidence. Click a recorded cell for its actual answer, tool guard, checks, raw response and optional answer audio.
- Model-call and token metrics reported for that admission run. Missing data says Not reported, not zero. Source extraction, transcription and exploratory costs are explicitly excluded. No invented account-credit estimate or safety score.
- Saved-proposal counts from the existing bounded GET /api/candidates list. Bars filter the proposal selector. Selecting a proposal loads its latest saved admission run and source without generation calls.
- Current approved-memory active/expired availability from the backend snapshot. The chart opens the management section; revoked records are not mislabeled expired.
- Counts and drilldown for loaded review events. Partial histories/lists are labeled; they are not represented as workspace-wide totals.

No new backend endpoint, migration, benchmark change or aggregation was introduced. Prior admission runs remain available through saved run links/history; the proposal picker loads each proposal's latest admission run. Scope experiment results remain separately labeled and cannot unlock approval.

## Template integration

- SimpleUse.tsx supplies the compact workflow indicator/test control.
- Dashboard.tsx owns read-only selectors, graphs and drilldowns. It accepts existing evidence/experiment/memory components as slots.
- workspace.css scopes page structure and chart geometry to their classes and consumes the existing color tokens. Replace visual tokens/layout without changing data calculations or gating.
- App owns shared state and the page URL. Existing source, test, decision and voice components are reused rather than keeping two independent copies of the proposal editor.

URL state: page=use or dashboard; panel=overview/evidence/experiments/memory. Existing candidate, run, experiment, audio_source and execution parameters are preserved. Do not change display text without updating the accessible-name browser tests.

## Verification

Production TypeScript/Vite build passed. The 23 browser tests cover existing upload/revision/approval/revoke/voice flows plus navigation, saved evidence loading, graph counts and filtering, pending/error cells, missing/unavailable data, no model requests during dashboard browsing, reload/back behavior, mobile overflow, keyboard scrolling of the matrix, and cancelling hidden microphone capture. Desktop/mobile captures were inspected. Review-data responses in these tests are explicitly synthetic; the proxy health check reaches the real local backend. No new live generation or paid speech requests were made for this UI change.
