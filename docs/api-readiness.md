# Integrated API-key test readiness

Integration branch: `integration/governed-memory-review`. Main is unchanged.

Corrected the Agent C sync/async mismatch, invalid exception class, removed/nonexistent SDK calls, missing profile IDs, recursive semaphore acquisition, retry accounting and conflicting dependency pins. Replaced placeholder tracing with bounded metadata-only best-effort export. Integrated Agent B's latest governance UI, honored its inbox removal, and replaced handwritten wire shapes with generated contract types.

Local checks: 95 backend tests passed, 2 credential-dependent tests skipped; TypeScript/Vite production build passed; Python pip check passed. Browser suite covers review/revision/approval/reload, stale approval, polling, errors, explicit synthetic mode, real local health proxy and governed expiry/version-bound revoke. Provider facade tests use explicit fakes; they do not claim network verification.

Verdict: ready for controlled API-key testing, not yet verified end to end against live services. No live credentials were supplied or used. The no-key embedding preflight correctly reports configuration_unavailable with a nonzero exit.

Use a new ignored `.env` in this integration checkout, based on `.env.example`, with MONGODB_URI, DEEPSEEK_API_KEY and VOYAGE_API_KEY. Keep optional voice and tracing off initially. No OpenAI key is required for this default combination. Run the sequence in integrations-setup.md; require all nonoptional preflight checks to pass before running the UI admission workflow. Admission uses 12 generation calls across three requests and is bounded by MAX_RUN_MODEL_CALLS=80; budget accordingly. Seed/index operations require database and Search permissions. Re-run preflight after model/profile changes. Real rate limits, billing, account model permissions and search readiness remain live checks.
