"""Pure tests for the verdict logic. No database, no LLM."""
from membrane.compare import build_comparison, decision, matches

REFUND_RETURN = {"tool_calls": [{"name": "issue_refund", "args": {"return_required": True}}]}
REFUND_KEEP = {"tool_calls": [{"name": "issue_refund", "args": {"return_required": False}}]}
NO_TOOL = {"tool_calls": []}

TASKS = {
    "vip_4821": {"_id": "vip_4821", "tenant_id": "store_a", "customer": {"tier": "VIP"},
                 "order": {"id": "4821"}, "message": "m",
                 "expected": {"tool": "issue_refund", "return_required": True},
                 "exception_expected": {"tool": "issue_refund", "return_required": False}},
    "vip_5530": {"_id": "vip_5530", "tenant_id": "store_a", "customer": {"tier": "VIP"},
                 "order": {"id": "5530"}, "message": "m",
                 "expected": {"tool": "issue_refund", "return_required": True}},
    "shipping": {"_id": "shipping", "tenant_id": "store_a", "customer": {"tier": "VIP"},
                 "order": {"id": "9001"}, "message": "m", "expected": {"tool": "no_tool"}},
    "b_vip": {"_id": "b_vip", "tenant_id": "store_b", "customer": {"tier": "VIP"},
              "order": {"id": "2207"}, "message": "m",
              "expected": {"tool": "issue_refund", "return_required": True}},
}


def make_run(outcomes, trials=3):
    """outcomes: {task_id: (result_in_A, result_in_B)}"""
    results = []
    for tid, (a, b) in outcomes.items():
        for view, out in (("A", a), ("B", b)):
            results += [{"task_id": tid, "view": view, "trial": t, **out} for t in range(trials)]
    return {"task_ids": list(outcomes), "results": results}


BROAD = {"tenant_id": "store_a", "scope": {"kind": "global"}}
NARROW = {"tenant_id": "store_a", "scope": {"kind": "order", "order_id": "4821"}}


def test_decision_reads_tool_arguments_not_text():
    said_return_but_waived = {"tool_calls": [{"name": "issue_refund", "args": {"return_required": False}}],
                              "final_text": "Please send the item back."}
    assert decision(said_return_but_waived) == ("issue_refund", False)
    assert not matches(decision(said_return_but_waived), {"tool": "issue_refund", "return_required": True})


def test_broad_vip_rule_fails():
    run = make_run({"vip_4821": (REFUND_RETURN, REFUND_KEEP), "vip_5530": (REFUND_RETURN, REFUND_KEEP),
                    "shipping": (NO_TOOL, NO_TOOL), "b_vip": (REFUND_RETURN, REFUND_RETURN)})
    out = build_comparison(run, TASKS, BROAD)
    assert out["verdict"] == "fail"
    assert out["effect"] == "out_of_scope"
    by = {c["task_id"]: c for c in out["cases"]}
    assert by["vip_5530"]["status"] == "fail"
    assert by["vip_5530"]["diff"] == [{"field": "return_required", "from": True, "to": False}]
    assert by["shipping"]["status"] == "pass" and by["b_vip"]["status"] == "pass"


def test_narrow_exception_passes_and_changes_only_its_order():
    run = make_run({"vip_4821": (REFUND_RETURN, REFUND_KEEP), "vip_5530": (REFUND_RETURN, REFUND_RETURN),
                    "shipping": (NO_TOOL, NO_TOOL), "b_vip": (REFUND_RETURN, REFUND_RETURN)})
    out = build_comparison(run, TASKS, NARROW)
    assert out["verdict"] == "pass"
    assert out["effect"] == "in_scope_only"
    assert [c["task_id"] for c in out["cases"] if c["changed"]] == ["vip_4821"]


def test_narrow_scope_does_not_excuse_changes_elsewhere():
    run = make_run({"vip_4821": (REFUND_RETURN, REFUND_KEEP), "vip_5530": (REFUND_RETURN, REFUND_KEEP)})
    assert build_comparison(run, TASKS, NARROW)["verdict"] == "fail"


def test_same_order_id_in_another_tenant_is_not_in_scope():
    tasks = {**TASKS, "b_4821": {**TASKS["vip_4821"], "_id": "b_4821", "tenant_id": "store_b"}}
    run = make_run({"b_4821": (REFUND_RETURN, REFUND_KEEP)})
    out = build_comparison(run, tasks, NARROW)
    assert out["cases"][0]["in_candidate_scope"] is False
    assert out["verdict"] == "fail"


def test_flaky_candidate_fails_when_any_trial_breaks_policy():
    run = make_run({"vip_5530": (REFUND_RETURN, REFUND_RETURN)})
    run["results"][-1] = {"task_id": "vip_5530", "view": "B", "trial": 2, **REFUND_KEEP}
    out = build_comparison(run, TASKS, BROAD)
    assert out["verdict"] == "fail" and out["cases"][0]["B"]["passed"] == "2/3"


def test_memory_with_no_effect_is_reported():
    run = make_run({"vip_5530": (REFUND_RETURN, REFUND_RETURN), "shipping": (NO_TOOL, NO_TOOL)})
    out = build_comparison(run, TASKS, BROAD)
    assert out["verdict"] == "pass" and out["effect"] == "none"


def test_failing_baseline_or_agent_error_is_inconclusive():
    run = make_run({"vip_5530": (REFUND_KEEP, REFUND_KEEP)})
    assert build_comparison(run, TASKS, BROAD)["verdict"] == "inconclusive"
    run = make_run({"vip_5530": (REFUND_RETURN, {"tool_calls": [], "error": "timeout"})})
    assert build_comparison(run, TASKS, BROAD)["verdict"] == "inconclusive"
