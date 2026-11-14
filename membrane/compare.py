"""Turn raw A/B runs into a verdict.

We compare ACTIONS (the tool the agent called and its arguments), not what the agent said.
`build_comparison` is pure: no database, no LLM. That is what the unit tests exercise.

Rules
- A change is allowed only inside the candidate's own scope (its tenant + its order).
- Every case outside that scope must still match the written policy (`expected`).
- If the baseline (View A) already fails a case, the run is inconclusive, not a pass.
"""
from __future__ import annotations

from collections import Counter


def decision(result: dict) -> tuple:
    """Reduce one agent run to (tool, return_required)."""
    if result.get("error"):
        return ("error", None)
    for call in result.get("tool_calls") or []:
        if call.get("name") == "issue_refund":
            return ("issue_refund", (call.get("args") or {}).get("return_required"))
        if call.get("name") == "deny_refund":
            return ("deny_refund", None)
    return ("no_tool", None)


def matches(dec: tuple, expected: dict) -> bool:
    tool, return_required = dec
    if expected.get("tool") != tool:
        return False
    return "return_required" not in expected or expected["return_required"] == return_required


def describe(dec: tuple) -> str:
    tool, rr = dec
    if tool == "issue_refund":
        if rr is True:
            return "Refund, return required"
        if rr is False:
            return "Refund, return waived"
        return "Refund (return_required missing)"
    return {"deny_refund": "Refund declined", "no_tool": "Answered, no refund tool",
            "error": "Run failed"}.get(tool, tool)


def _majority(decs: list[tuple]) -> tuple:
    return Counter(decs).most_common(1)[0][0]


def _diff(a: tuple, b: tuple) -> list[dict]:
    out = []
    if a[0] != b[0]:
        out.append({"field": "tool", "from": a[0], "to": b[0]})
    if a[1] != b[1]:
        out.append({"field": "return_required", "from": a[1], "to": b[1]})
    return out


def build_comparison(run: dict, tasks: dict, candidate: dict) -> dict:
    """run: simulation_runs doc. tasks: {task_id: fixture}. candidate: memory_versions doc."""
    scope = candidate.get("scope") or {}
    cases = []
    for tid in run["task_ids"]:
        task = tasks[tid]
        views = {}
        for view in ("A", "B"):
            decs = [decision(r) for r in run["results"]
                    if r["task_id"] == tid and r["view"] == view]
            views[view] = decs
        if not views["A"] or not views["B"]:
            continue

        intended = (
            scope.get("kind") == "order"
            and task["tenant_id"] == candidate["tenant_id"]
            and str(task["order"]["id"]) == str(scope.get("order_id"))
        )
        expected_a = task["expected"]
        # Inside the candidate's scope the target is the approved-exception outcome, if the
        # fixture defines one. Outside it, the written policy is the only acceptable outcome.
        expected_b = task.get("exception_expected", None) if intended else task["expected"]

        a_pass = sum(matches(d, expected_a) for d in views["A"])
        if expected_b is None:  # in scope, no stated target: any change is the reviewer's call
            b_pass = sum(d[0] != "error" for d in views["B"])
        else:
            b_pass = sum(matches(d, expected_b) for d in views["B"])
        n_a, n_b = len(views["A"]), len(views["B"])
        maj_a, maj_b = _majority(views["A"]), _majority(views["B"])
        errored = any(d[0] == "error" for d in views["A"] + views["B"])

        baseline_ok = a_pass == n_a
        b_ok = b_pass == n_b
        changed = Counter(views["A"]) != Counter(views["B"])
        if errored:
            status = "error"
        elif not baseline_ok:
            status = "baseline_fail"
        elif not b_ok:
            status = "fail"
        else:
            status = "pass"

        cases.append({
            "task_id": tid,
            "tenant_id": task["tenant_id"],
            "customer_tier": task["customer"]["tier"],
            "order_id": task["order"]["id"],
            "message": task["message"],
            "in_candidate_scope": intended,
            "expected": expected_b if expected_b is not None else expected_a,
            "A": {"decision": list(maj_a), "label": describe(maj_a), "passed": f"{a_pass}/{n_a}"},
            "B": {"decision": list(maj_b), "label": describe(maj_b), "passed": f"{b_pass}/{n_b}"},
            "changed": changed,
            "diff": _diff(maj_a, maj_b) if changed else [],
            "status": status,
        })

    statuses = [c["status"] for c in cases]
    if not cases or "error" in statuses or "baseline_fail" in statuses:
        verdict = "inconclusive"
    elif "fail" in statuses:
        verdict = "fail"
    else:
        verdict = "pass"

    changed_cases = [c for c in cases if c["changed"]]
    if not changed_cases:
        effect = "none"            # the memory changed no tested action
    elif all(c["in_candidate_scope"] for c in changed_cases):
        effect = "in_scope_only"   # it changed behavior only where it was meant to
    else:
        effect = "out_of_scope"    # it changed behavior somewhere it had no business

    reasons = []
    for c in cases:
        if c["status"] == "fail":
            d = "; ".join(f"{x['field']}: {x['from']} -> {x['to']}" for x in c["diff"]) or "wrong action"
            reasons.append(f"{c['task_id']} ({c['tenant_id']}, order {c['order_id']}): {d}")
        elif c["status"] == "baseline_fail":
            reasons.append(f"{c['task_id']}: current memory already fails this case")
        elif c["status"] == "error":
            reasons.append(f"{c['task_id']}: an agent run failed")
    return {"cases": cases, "verdict": verdict, "effect": effect, "reasons": reasons}


def compare(run_id: str) -> dict:
    """Load a run, compare it, store the result on the run."""
    from .db import get_db

    db = get_db()
    run = db.simulation_runs.find_one({"_id": run_id})
    if not run:
        raise ValueError("run not found")
    candidate = db.memory_versions.find_one({"_id": run["candidate_id"]})
    tasks = {t["_id"]: t for t in db.task_fixtures.find({"_id": {"$in": run["task_ids"]}})}
    result = build_comparison(run, tasks, candidate)
    db.simulation_runs.update_one(
        {"_id": run_id},
        {"$set": {"comparison": result["cases"], "verdict": result["verdict"],
                  "effect": result["effect"], "reasons": result["reasons"]}},
    )
    return result
