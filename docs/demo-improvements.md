# Demo improvements after the visual refresh

The visual refresh is implemented. The ideas below are proposals, not implemented features.

1. Ground-truth drawer: trusted task facts, matching exception record, policy version, expected action and actual attempt together. Use persisted frozen task/policy evidence, not a fresh LLM judgment; clearly mark unavailable legacy evidence. Highest priority because it explains the verdict. No new provider calls.
2. Scope boundary challenge: show the same intent for order 4821 and another VIP order side by side. Reuse existing selected cases where possible; otherwise run two explicitly labeled exploratory tasks through the bounded execution path. Do not silently inject a draft candidate into active memory. This demonstrates overgeneralization visually.
3. Memory lifecycle replay: before approval, after approval, after revoke. Show the version, retrieved memory IDs and actual action at each step. Existing execution/revoke routes support this, but real activation still requires eligible evidence and explicit approval. Never animate fabricated behavioral changes; show unchanged outcomes honestly.
4. Audio A/B: side-by-side play buttons for actual stored baseline/candidate answers using existing ElevenLabs endpoint/cache. Keep policy result visible and speaker/model identical. Requires optional key, voice ID and voice enabled; currently disabled. Never use speech as evaluation evidence.
5. Source-to-memory drift: highlight identifiers and quantifiers in the source quote and proposed sentence (one order versus all VIPs). Begin with deterministic matching, labeling it a review aid rather than a semantic safety guarantee. Source is still untrusted.
6. Evidence replay mode: saved real run with visible timestamp, model, policy/profile and recorded badge. Replaying should never incur new generation charges or imply a current live run. Existing persisted runs provide most data. Useful fallback for demo connectivity failures.

Recommended demo story: upload PDF -> inspect authority facts -> inspect boundary cases -> narrow memory -> test -> reviewer approval only if eligible -> try active agent -> revoke -> show actual exclusion from retrieval. A safe model resisting the broad memory is a valid result; do not promise a red-to-green performance.
