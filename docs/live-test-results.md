# Live test results — 2026-11-14

Real local credentials were used; none are recorded here. Frontend: http://127.0.0.1:5173; FastAPI: http://127.0.0.1:8000. Optional voice and tracing remain disabled.

## Passed

- Initialized isolated membrane-demo-v2 workspace and embedded synthetic fixtures/probe with Voyage.
- Both fixture_semantic_v2 and memory_semantic_v1 indexes became queryable; known-neighbor queries passed.
- Actual Atlas workspace access, DeepSeek generation and image extraction, and Voyage embeddings all passed preflight.
- Live health through the Vite proxy reports every required component ready.
- Following fixes/restart, POST /api/agent/tasks/development-01/execute returned a persisted execution with request_return, one generation call and no execution error: execution_05742f4a84304e5c824e245df524979d.
- Three additional direct synthetic decisions passed local schema validation with the clarified decision prompt.
- Offline regression suite: 96 passed, 2 opt-in live tests skipped.

## Full paired workflow did not pass

The smoke flow uploaded the real synthetic screenshot, staged a broad candidate, ran all 48 paired decisions, revised to the scoped exception, and ran another 48 decisions. Broad run run_a3f011c87e914310afd39f23cc5ac77c and narrow run run_5617d7a6a29541fb90d95090d7bbb115 both ended quarantined. Reasons included observed policy violations and incomplete/failed/usefulness evidence. Nothing was activated. Original results are preserved in Atlas and must not be relabeled as passing.

These paired runs used the original decision instructions. Malformed/schema-copy responses prompted a clarification that requires one actual JSON decision object. The corrected prompt passed three direct probes and one subsequent actual HTTP execution; a complete paired admission rerun has NOT yet been validated with the corrected prompt. Successful connectivity does not imply a safe or eligible candidate.

## Corrections made during testing

- Increased bounded Atlas connection/DNS timeout from 4 to 10 seconds to match the independently successful connection check.
- Explicitly instructed image extraction to produce valid identifier scope and an exact substring quotation; local validation remains strict.
- Explicitly required actual JSON decision values rather than a repeated schema; malformed responses still fail closed.

## Manual test

Open http://127.0.0.1:5173 with no synthetic query parameter. Use Run with active memory for a small live task. To test admission, upload fixtures/support-4821.png, stage a candidate, run the paired behavior test, inspect all evidence and only approve if eligible. The CLI alternative is `.\.venv\Scripts\python.exe -m scripts.backend_smoke`; it creates two 48-decision runs, potentially more calls on bounded transient retries, and does not activate anything without --approve.
