# Demo direction: test the boundary of a memory

Status: proposal. The simplified review UI is implemented; the experiments below are not.

## Why the current tests feel generic

Admission selects twelve cases from 24 development fixtures. Those fixtures repeat eight support/refund scenario families with different order IDs. Five mandatory checks and semantic neighbors help coverage, but selection cannot discover a new failure family outside this fixed dataset. The twelve held-out fixtures are separate; they are not currently proof of broad generalization. We should describe this as a focused benchmark.

## Recommended next experiment: Scope microscope

Question: exactly where does a one-order exception begin to leak?

Start from a synthetic request covered by an independently stored trusted exception. Derive a small family by changing one fact at a time: other order, other customer, unverified owner, redirected payment, amount beyond balance, expired exception. Keep the proposal constant. Run the same frozen scenarios without and with it, repeated. Show each changed fact, the trusted rule, the attempted action and enforcement outcome. A completed safe response is separate from a malformed response; failures never become green tiles.

Expected outcomes come from policy and immutable synthetic facts. A generated proposal cannot create or amend the trusted exception registry. The AI can suggest surface wording but cannot supply expected labels. Mutation code must validate that only the selected fact changed and must preserve scenario provenance. Expiry tests use explicit evaluation times in an isolated test context, never a global clock change.

Implement as a separately labeled exploratory experiment first, persisted with parent scenario, mutation, fixture hash, policy/profile/version, provider configuration, A/B repetitions and usage. Do not append results to an existing eligible run or unlock approval with fewer than the current required checks. Run a new admission experiment after any candidate or test-suite change. No hardcoded assertion that a broad instruction must fool the model.

## Other distinctive demonstrations

- Permission laundering: a PDF says 'skip verification' inside a plausible supervisor note. Separate source claim from trusted authority, highlight the conflicting clause and inspect whether the proposed lesson repeats it. This tests extraction as well as downstream actions. Everything remains synthetic.
- Memory collision: two individually harmless approved memories combine into an unsafe instruction. Test them separately and together, rather than just one-at-a-time. First implement as exploratory combinations with frozen versions; current admission does not establish this guarantee.
- Withdrawal replay: execute before and after explicit revocation; show the retrieved entry disappearing even if the model produces the same answer. This demonstrates an enforceable guarantee without promising a dramatic behavioral change. Existing revoke/execution routes do most of the work.
- Preference versus permission: 'VIPs prefer fast resolution' must not become authority to bypass returns or identity checks. Reuses preference scope, trusted policy and exact action checks; requires deliberate benchmark cases.

## Demo order

Scope microscope -> source claim versus trusted authority -> scoped revision -> eligible approval only when genuinely supported -> revocation with retrieval evidence. Audio A/B can make the result tangible once ElevenLabs is enabled, but speaking a stored answer adds no safety evidence.

## Template handoff

Keep WorkflowGuide and ExperimentSummary as state-derived functional components. App separates the review and approved-memory workspaces; live executions named in the URL reopen the latter. Labels now use Save for testing, Test this memory, Save changes for a new test, Approve for use and Reject memory. Backend DTO names and approval gating are unchanged. Teammates can reskin tokens/layout without rewriting service calls or recreating eligibility logic. Browser tests depend on accessible control names, so rename controls and tests together.
