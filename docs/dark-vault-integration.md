# Dark vault design integration

Branch: `integration/dark-vault-voice-scope`

Combines `feat/memory-experiments-voice-sources` with `origin/feat/dark-vault-ui` (1f1b19d). Main is unchanged. The separate Gmail branch is outside this integration.

## What changed

- Uses the dark vault palette, orange actions, security lock, and before/after example from the design branch.
- Keeps Upload and test as the simple workflow, with evidence, graphs, experiments and governed memory on Dashboard.
- Custom scope uses accessible radio cards; expiry offers 1-hour, 4-hour and 1-day presets plus custom minutes. Both still submit the existing backend contract.
- Source evidence is collapsed by default; reviewed voice playback remains available.
- Dashboard adds a read-only quarantine shelf using the existing bounded candidate list. Partial or unavailable lists are labelled.
- The lock opens only for confirmed active backend membership. Passing checks stays locked pending approval. Missing membership in a truncated list remains unknown.
- Verdicts distinguish new failures from baseline failures, inconclusive evidence, stale test revisions and approved memories that are no longer active.
- CSS loads in a single explicit order in main.tsx: base, workspace, dark vault.

## Preserved functionality

ElevenLabs upload/recording and explicit transcript review, DeepSeek proposal extraction, immutable candidate revisions, deterministic A/B checks, version-bound approval/withdrawal, saved evidence reloads, and exploratory scope experiments remain intact. Experiments cannot grant approval. No backend, credentials, provider selection or API contracts changed.

## Validation

Production TypeScript/Vite build passes. The 25-test Chrome browser suite covers PDF intake, voice review/cancellation, revision/approval, conflict handling, expiry/revocation, dashboard drilldown, exploration isolation, visual option payloads and security verdict state. Desktop and 390px mobile screenshots were inspected; the custom options do not overflow.

Browser APIs are synthetic fixtures except the existing local backend health smoke check. This is a UI integration check, not a fresh paid-provider end-to-end run.

## Final simplification

- The simple page now centers the lock and next action. Removed the four-step text strip, repeated verdict, case tallies and before/after panel from this page.
- After saving, the editor collapses to Edit memory. Source replacement and custom duration are secondary disclosures. Approval appears only for an eligible exact revision; manual rejection is a separate disclosure requiring a reason.
- Dashboard keeps the existing two tabs and APIs. Its initial view is a security verdict, clickable nonzero outcome counts and the four-decision matrix. Symbols retain screen-reader labels and the shared legend.
- Full evidence, scope experiments, quarantine and usage/history statistics are grouped under Evidence and tools. Saved evidence and experiment URLs open the necessary disclosures automatically.
- The phone comparison grid fits all four decisions without sideways scrolling. Keyboard focus, selection and drilldown remain functional.
- Design reference: https://www.nngroup.com/articles/progressive-disclosure/ (prioritize frequent decisions and disclose secondary controls).
