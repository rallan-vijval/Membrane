# Membrane

**Preview what a new memory will make your agent do.**

Built during *Agents in Context Toronto: a MongoDB Hackathon* (Nov 14, 2026).
Problem statement: **2. Memory You Can Govern.**

## The problem

Agents learn from what they see, and sometimes learn the wrong lesson. A manager approves one
exception: "Order 4821 may be refunded without returning the item." The agent remembers
"VIP customers may keep refunded items." Nothing in that sentence looks malicious, so a content
scanner passes it, and the agent quietly starts waiving returns for every VIP.

## What Membrane does

A new memory is tested before the agent may keep it.

1. **Stage.** The proposed memory is stored as `proposed`. The live agent cannot see it.
2. **Run two views.** The same frozen tasks run in fresh sessions: View A with current memory,
   View B with current memory plus the candidate. Refund tools are simulated.
3. **Compare actions.** We diff the tool calls (`return_required: true -> false`), not the wording.
4. **Decide.** A candidate that breaks policy outside its own scope is quarantined. It can be
   revised (narrowed to order 4821) and retested. Only a passing run can be accepted.

## How it answers the track's questions

| Question | Answer in this repo |
| --- | --- |
| Keep one client's memory from leaking into another's? | Every memory has a `tenant_id`. It is a pre-filter inside `$vectorSearch` and re-checked on the live document. Every test run includes a Store B case. |
| Fix or drop a memory that is wrong or expired? | Versioned memories: `revise` creates a new version that supersedes the old one once it passes; `revoke` forgets; `expires_at` is enforced in the retrieval query. |
| Prove a memory changed behavior and didn't just fill the prompt? | The A/B run: identical task, identical session setup, the only difference is the memory, and the recorded tool arguments differ. A memory that changes nothing is reported as `effect: none`. |

## How MongoDB Atlas is used

- `memory_versions`: every memory version with tenant, scope, status, expiry, source and history.
- `sources`: where each memory came from.
- `task_fixtures`: frozen, synthetic support cases with hand-written expected outcomes.
- `simulation_runs`: every A/B run with each tool call, the comparison and the review decision.
- **Vector Search (auto-embedding, Voyage `voyage-4`)** does two jobs:
  - `fixture_vec` picks the past cases most related to a candidate memory, so the right tests run.
  - `memory_vec` retrieves the agent's memory, with tenant, status, expiry and scope as filters.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # add MONGODB_URI and LLM_API_KEY
python -m membrane.db                                  # should print {'ok': 1.0}
python -m scripts.setup_indexes                        # once; indexes take a minute to build
python -m scripts.reset_demo                           # clean demo state
uvicorn membrane.app:app --reload                      # open http://127.0.0.1:8000
```

## Demo flow

1. **Load example** then **Stage memory**: the broad VIP rule is staged for `store_a`.
2. **Run A/B test**: VIP cases flip to "return waived" in View B and the verdict is FAIL.
3. **Quarantine**, or **Revise: narrow to one order** (4821), then test again: only order 4821
   changes, Store B is untouched, verdict PASS.
4. **Accept** (optionally with a short expiry), then use **Live agent check** on order 4821 and
   order 5530 to see that only 4821 changed. Revoke it, or let it expire, and check again.

## Tests

```bash
pytest
```

- `tests/test_compare.py`: the verdict logic (pure, no database or LLM).
- `tests/test_agent.py`: the agent wrapper with the HTTP call faked.
- `tests/test_governance.py`: isolation, scope, tenant, expiry, revoke, supersede and audit rules
  against the real Atlas cluster (skipped when `MONGODB_URI` is not set; uses its own test tenants).

## Limits

- Tests are evidence for the selected cases, not a safety guarantee. Scope, expiry and revoke
  exist because a bad memory can still pass.
- Expected outcomes are written by people from the policy. The model never grades itself.
- All customers, orders and refunds are synthetic. The refund tools only record their arguments.

## Layout

```
membrane/
  db.py         Atlas connection
  fixtures.py   synthetic cases + policy
  memory.py     stage, governed retrieval, accept, quarantine, revise, revoke, audit
  agent.py      support agent + simulated refund tools (Anthropic or OpenAI)
  selector.py   Vector Search test selection
  runner.py     A/B runs in isolated sessions
  compare.py    action diff + verdict
  app.py        FastAPI endpoints
  static/       the review page (plain HTML)
scripts/        setup_indexes.py, reset_demo.py
tests/
```
