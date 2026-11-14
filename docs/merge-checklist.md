# Shared integration, then branch split

Current user instruction: wait for the other agent's handoff, merge both contributions to `main`, then split into new branches from that common point. No main merge has been performed at this checkpoint.

## Before integration

- Teammate supplies frontend branch/commit, confirms no uncommitted changes are omitted, and lists actual install/typecheck/build/browser checks and remaining blockers. Observed candidate: `feat/membrane-review-ui` at `f061fe8`; a published commit alone is not a readiness confirmation.
- Both agents have pushed clean committed work. Preserve current backend on `feat/membrane-backend`; do not take over or rewrite the frontend branch.
- Fetch remote refs and compare files owned by each agent. Verify `main` has not advanced unexpectedly. Preserve new teammate commits; never force-push shared history.

## Integration sequence after handoff

1. Check out the existing `main` worktree with a clean working tree and fast-forward to remote `main` if possible. If histories diverge, inspect and merge without dropping either side.
2. Merge the reviewed backend branch, then the handed-off frontend branch. Resolve shared docs/config deliberately and keep both API implementations recognizable until a separate retirement decision is made.
3. Ensure frontend API base/proxy points to `backend.app.main:app`, not the legacy entrypoint. Check source upload, run polling, exact error envelopes, enum values, idempotency headers, paired repetitions, and audio response types against `contracts/openapi.yaml`.
4. Install with the frontend's chosen package manager and commit its reproducible lockfile if missing; run typecheck/build and the teammate's browser smoke. Backend checks: `python -m pytest backend/tests tests -q`, generated-contract consistency, and `git diff --check`.
5. Run the labeled synthetic UI flow and verify unavailable real integrations never silently fall back to mocks. Once credentials exist, run real preflight plus broad→review→scoped revision→exact approval→reload/restart. If unavailable, retain an explicit external-blocker record; do not claim connected acceptance.
6. Update `docs/CHANGELOG.md` with both source commit IDs, the resulting shared merge commit, checks, conflicts resolved, and any remaining blockers. Push the reviewed `main` result.

## Split after the shared merge

Both agents fetch the same resulting `origin/main` commit and create their next separate branches from it. Agree on the next assignments before editing shared files. Keep backend ownership on Agent A and frontend ownership on Agent B unless the team explicitly changes the split. Choose names that describe the next agreed task; do not create empty speculative branches now.
