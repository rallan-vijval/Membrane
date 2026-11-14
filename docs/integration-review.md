> Update: blockers corrected on the integration branch. See [current readiness](api-readiness.md) and [correction log](integration-fix-log.md). The review below records the originally submitted checkpoints.

# A/B/C integration review — November 14, 2026

Main is unchanged at `9b36508`. Review is isolated from the agents' source branches.

| Contribution | Reviewed commit | Status |
| --- | --- | --- |
| A: `feat/governed-memory-backend` | `85a12d0` | Backend/contract tested; provider facade integration awaits fixes below |
| B: `feat/governed-memory-ui` | `49c66a5` | A+B staging merge is clean; build/base browser flow pass; assigned governance controls still missing |
| C: actual branch `feat/provider-integration` (singular) | `fd06608` | **Do not merge as ready**: concrete runtime/interface/dependency blockers |

The originally planned C branch name was `feat/provider-integrations`; use the actual singular remote branch above for this review. A staged A+B worktree is at `C:\MongoDB\membrane-integration`, branch `integration/governed-memory-review`. Its merge does not affect main or any source branch. C was inspected in a detached review worktree; no C source files or dependency pins were installed/modified.

## C findings requiring correction

### P1 — Error type cannot be raised or caught

`backend/app/integrations/api.py:55` declares `IntegrationFailure` as a dataclass without inheriting `Exception`. Every `raise IntegrationFailure(...)` fails with `TypeError: exceptions must derive from BaseException`; `except IntegrationFailure` is invalid too. Reproduced locally without network calls. Make it a real sanitized exception, test raising/catching, and keep secrets out of its message/repr.

### P1 — Async facade/semaphore differs from the agreed synchronous seam

`api.py:70` and `:80` require coroutine methods and an `asyncio.Semaphore`. A's single-process threaded FastAPI worker uses synchronous calls and passes a `threading.BoundedSemaphore(2)`. Calling C's method currently returns a coroutine rather than `EmbeddingBatch`; that semaphore has no async context manager. Reproduced `inspect.iscoroutinefunction(client.embed_query) == True` and missing `__aenter__` on A's semaphore.

Preferred fix: C implements synchronous public methods using the supplied threading semaphore and current synchronous SDK clients, matching the phase plan. Do not add event-loop wrappers to A to mask multiple broken SDK/retry paths. If the team intentionally chooses async instead, revise the Python interface and all callers together before claiming compatibility.

### P1 — Required profile ID is absent from describe()

`provider_openai.py:97` and `provider_voyage.py:118` omit `profile_id`. A needs `describe()['profile_id']` before seeding/freezing/retrieval. Both clients compute a private profile hash, but do not expose it in the method the contract specifies. Include provider/model/dimensions **and input conventions/version** in the same deterministic profile returned by describe/batches/probes. A profile must not include the key.

### P1 — SDK calls and dependency pins are incompatible

`provider_openai.py:64` calls `openai.Embedding.acreate`, removed in OpenAI SDK v1+. Local evaluation with our installed SDK 3.51.0 reproduces `APIRemovedInV1` before any network call. C pins `openai==1.30.0`, which also uses the post-v1 SDK interface and conflicts with A's exact `openai==3.51.0` requirement. Its `pytest==8.2.2` also conflicts with current `pytest==9.2.0`.

Use explicit SDK client instances and current `client.embeddings.create`, not module-global API keys. Voyage currently calls module-level `voyageai.embeddings.create` (`provider_voyage.py:56`/`:89`), whereas the documented SDK API is `voyageai.Client(...).embed(...)`; validate the pinned version's real API with transport mocks. Return actual SDK result fields rather than assuming a dictionary. Pass output dimensions explicitly and Voyage `truncation=False` plus document/query modes.

C must not downgrade the shared OpenAI/pytest packages. Keep integration-specific runtime dependencies in its owned requirements file; A aggregates/pins after compatible install. No dependency changes from C have been applied to the tested A+B environment.

### P1/P2 — Retry/probe/usage behavior does not satisfy the contract

- `provider_openai.py:52` and `provider_voyage.py:44` retry by awaiting the **same coroutine object**. A completed/failed coroutine cannot be awaited a second time. Construct a fresh SDK request for each allowed transient retry; do not retry validation/auth failures.
- Success always reports `attempted_calls=1`, even after a retry. Elapsed time derives from a usually absent `_request_timestamp`, so it is not measured call latency. Validate vector count as well as length, and account for each actual request.
- `api.py:167` acquires the semaphore outside `client.probe()`, while probe acquires it again internally. This can deadlock a single-slot semaphore or saturate all slots under concurrent probes. Acquire once around each SDK request.
- Probe comments claim no paid calls, but probe embeds text. Correct the billable warning and make the command inspect only the explicitly selected provider; a DeepSeek+Voyage setup must not fail because no unused OpenAI key exists.
- `message=str(exc)`/generic exception strings are propagated to probe output. Convert errors into fixed sanitized codes/messages; do not expose SDK response bodies or credentials.

### P2 — LangSmith is a placeholder, and tests/handoff are absent

`api.py:139` explicitly says a real implementation would POST to LangSmith. No client submission, bounded background queue or trace URL exists; requirements do not include LangSmith. Do not advertise working tracing. Implement the planned bounded best-effort tracer, or explicitly defer it and report disabled/unavailable.

`backend/integrations_tests/` is absent despite the setup doc claiming a suite. `docs/agent-c-progress.md` is absent too. Supply actual facade/SDK/retry/semaphore/dimension/redaction tests, commands/results, and accurate blockers before readiness handoff.

### A-side integration follow-up

C exposes `TracerConfig`, while A currently sends a dictionary to `create_tracer`. Once the interface is corrected, A must construct C's typed config and verify the optional tracer. A's safety wrapper catches failure so this cannot alter admission, but that is not proof tracing works. This compatibility adjustment belongs to A, not an unannounced change in C's files.

## B findings and staging fixes

- No merge conflicts against A. New inbox maps to the existing `/api/tasks` and active execution endpoints. Its provisional unknown/alternative-field adapters have been replaced **only on the review branch** with canonical generated `TaskOptions`/`ActiveExecution` types and exact `retrieval.entries` mapping. Added an inbox browser contract test.
- B's log lists lifetime picker, expiry/revoke panel, per-case memory retrieval, trace links and updated runbook as not started. These are still incomplete relative to Task B, even though their inbox/restyle work is handed off. Regenerate the current contract, finish those owned UI tasks or explicitly agree to defer them; do not call the whole governed-memory UI complete.
- Multi-format intake is a browser conversion to one image: PDF first page, text with a visible truncation cap, or selected video frame. It is not whole-document/video extraction. Additional format tests and durable conversion provenance need review before broader claims. No real Gmail integration or sending is present.
- The new terminal-poll ordering fix is valuable; add a test where candidate eligibility changes only on the final poll (not immediately at run creation) so that race stays covered.

## Verified checks and what they prove

On staged A+B with existing compatible dependencies: clean offline lockfile install, canonical TS generation, TypeScript/production build, **89 Python tests passed / 2 live checks skipped**, and **7 Playwright tests passed** (existing six plus exact inbox request/retrieval/enforcement mapping). npm reports zero dependency findings for that frontend lockfile.

Browser review/inbox responses are explicit synthetic HTTP fixtures; an unmocked test reaches real local FastAPI health through Vite with the worker disabled. These checks do not prove C's package works or establish live Atlas/Voyage/DeepSeek success. C inspection used local type/signature/SDK checks only; no provider network request, secret or paid call was used.

## Proposed final merge sequence

1. C fixes the blocking facade/SDK/dependency/test issues on its own branch and hands over a new commit plus actual checks. Optional tracing may be honestly deferred.
2. A validates the Python seam against that commit, makes its typed tracer-config adjustment, adds compatible integration dependencies and regenerates the aggregate lock; run both owners' test suites and check missing-key health states.
3. B aligns the remaining governance controls and regenerated DTOs with A's published contract; use the staged typed inbox adapter/test as an integration patch, not a reason to rewrite B's branch.
4. From reviewed current main, merge C → A → B plus the reviewed staging compatibility patch. Rerun Python, build and browser suites. Keep live credential-dependent checks explicitly pending until configured.
5. Only then update shared `docs/CHANGELOG.md` and push main. Source branches stay intact. Do not merge older superseded `feat/membrane-review-ui` commits.
