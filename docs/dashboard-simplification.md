# Dashboard language and disclosure update

Replaces the earlier four dashboard sections with two:

- **Test results:** what happened when a proposed memory was tested. Select the memory to inspect; the primary view is an outcome chart and a clickable before/after decision matrix.
- **Memory in use:** memories already approved for use, including their active/expired status and the option to withdraw an entry. Approval itself remains in the Upload and test workflow.

The selector is called Memory to inspect, not Saved proposal. Test evidence is Full test details beneath the current result. Scope experiments are Try harder cases beneath that same memory, with a Test nearby cases action. Usage, review-status graphs and decision-history graphs are grouped under More statistics. These supporting sections are closed by default; explicit detail links and stored experiment URLs still reopen the corresponding evidence.

Connection checks moved from the header into collapsed Settings. Optional disabled services say Not in use; configured services without a live health result say Not checked. No configuration or eligibility rule changed. Raw version IDs and memory origins are disclosed only when requested. Revoke is labeled Withdraw with the same server-side action.

The default dashboard uses essential labels and real observed data only. Zero outcome categories are omitted; missing/partial data stays clearly identified. Matrix column groups explicitly say Without this memory and With this memory. Failures to obtain usable evidence are labeled Could not check and remain separate from failed policy checks.

Navigation, persisted detail links, upload/review/approval, withdrawal, voice capture, saved-result loading, graph filtering/drilldown, missing-data states and responsive layout are covered by the browser suite. No new backend endpoints or paid provider calls were introduced. Existing visual tokens are retained for the team's later design template.
