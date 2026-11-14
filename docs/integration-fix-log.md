# Integration correction log

2026-11-14 — Integration owner corrected blockers after reviewing A/B/C.

- Integrated latest B governance UI and C provider package on isolated review branch.
- Provider facade now follows backend synchronous/thread semaphore contract; safe real exceptions, validated finite vectors/counts, stable profile, current SDK calls, transient-only bounded retries and sanitized failures.
- Dependency pins reconciled with application; full installed lock refreshed.
- Tracing configuration now typed; optional export bounded and metadata-only, no blocking business requests.
- Preflight uses only selected provider; absent credentials fail explicitly.
- Frontend contract types regenerated; handwritten governance DTOs removed and obsolete inbox adapter/test removed per B's intentional removal.
- Added provider regression and governed-memory browser checks. See api-readiness.md for results and live limitations.

Previous review blockers in integration-review.md describe the original submitted C checkpoint; this log and api-readiness.md supersede those blocker statuses for this integration branch.

## Agent B checkpoint 4 integration verification

Reviewed 5d22cf6 against main a8520c6. This checkpoint adds seven browser tests and the B progress log only; it changes no application code or dependencies. Merged without conflicts or required adjustments. Production TypeScript/Vite build passed. All 14 Playwright tests passed under the committed configuration, using system Chrome, Vite and the actual local FastAPI health endpoint. Governance requests use explicitly synthetic intercepted fixtures; live provider calls were not run. This resolves checkpoint 4's earlier local proxy-test limitation.

## Local cleanup before credential testing

Consolidated the working checkout into C:\MongoDB\membrane on main. Removed clean obsolete backend/frontend/provider-review/integration worktrees after recreating the Python environment and frontend dependencies in the main checkout. Branches/history remain available. Kept offline npm tooling under C:\MongoDB\.tools and preserved integration screenshots under artifacts/integration-review. Created an ignored local .env from the example with blank credentials.

A fresh .env exposed the legacy Atlas test module loading configuration during collection. It now requires RUN_LIVE_INTEGRATION=1 before loading .env, matching the backend live-test opt-in and preventing ordinary test collection from enabling database tests or contaminating offline settings. Verified in the canonical checkout: 95 passed, 2 skipped; pip check and frontend production build passed.


## Remote main and configuration integration

Integrated remote main 17eb393. Retained frontend/render.yaml as an explicitly synthetic static demo and changed its build to npm ci for lockfile consistency. Removed the unverified DeepSeek /embeddings client and factory option: application Settings never accepted that provider, and generation/vision already use the dedicated DeepSeek Responses integration. Voyage remains the selected embedding provider. Added a regression that rejects DeepSeek embedding configuration.

Simplified .env.example into database, DeepSeek, Voyage, limits and optional-service sections; removed legacy static-demo variables from the active template. The ignored local .env was normalized without changing supported values, and its original was preserved in ignored .env.before-cleanup. No credentials committed. Local live test remains blocked by an unfinished MongoDB URI and missing DeepSeek/Voyage keys.

Verification: 96 backend tests passed, 2 live checks skipped; pip check and TypeScript/Vite build passed. All 14 browser tests passed with the canonical checkout/configuration.


## Live credential test

Initialized the v2 workspace and both search indexes. Corrected bounded Atlas connection timeout and strict extraction/decision instructions after observing live failures. Full results, successful probes and the unsuccessful original paired admission workflow are recorded in live-test-results.md. No memory activated.

## PDF upload fix

Vite's dynamic-import helper added ?import to the public PDF.js module URL and tried to transform the public asset. Resolve the module to a fully qualified same-origin URL before importing it; Vite then leaves the public module untouched. The worker URL and lazy loading remain intact. Added the synthetic one-page PDF fixture and a browser regression exercising real PDF.js and its worker. No overlay suppression. Production TypeScript/Vite build passed; all 15 browser tests passed against the running local Vite/FastAPI servers using a temporary configuration that did not start duplicate servers. API review fixtures in browser tests remain synthetic.

## Visual review refresh

Added a state-driven five-stage journey and next-step guidance, a distinct A/B experiment boundary, and case-outcome counts separating new violations, baseline violations, inconclusive evidence, safe changes and unchanged-safe cases. Active-memory exploration is visually separated from admission testing. Updated typography, spacing, teal/paper palette and responsive layouts. Outcomes remain derived from backend classifications and approval authority is unchanged. Production build and all 15 browser tests passed against running local servers; desktop and mobile screenshots inspected. Future demo proposals are recorded separately in demo-improvements.md.
