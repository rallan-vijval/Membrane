from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.app.common import Problem
from backend.app.fixtures import BROAD, NARROW
from backend.app.models import CandidateIn, Scope, ReviseIn
from backend.app.runner import Worker


def stage(env, narrow=False):
    cfg, store, provider, service, source = env
    return service.stage(CandidateIn(source_id=source["source_id"], text=NARROW if narrow else BROAD,
        scope=Scope(kind="order", order_id="4821", customer_id="customer-4821", exception_id="exc-4821") if narrow else Scope(),
        base_version_id=store.active()["version_id"]))


def execute(env, candidate):
    _, store, provider, service, _ = env
    run_id = service.create_run(candidate["candidate_id"])["run_id"]
    worker = Worker(service)
    run = worker.claim()
    assert run and run["run_id"] == run_id
    worker.execute(run)
    return worker.detail(run_id)


def test_full_broad_quarantine_narrow_approval_and_reload(env, fake_selection):
    _, store, provider, service, _ = env
    initial = store.active()["version_id"]
    broad = stage(env)
    assert store.active()["memories"] == []
    failed = execute(env, broad)
    assert failed["admission"] == "quarantine"
    denied = [e for c in failed["cases"] for e in c["executions"] if e["tool_outcome"] and not e["tool_outcome"]["allowed"]]
    assert denied and denied[0]["attempt"]["arguments"] and denied[0]["raw_responses"]
    assert store.active()["version_id"] == initial
    revised = service.revise(broad["candidate_id"], ReviseIn(text=NARROW,
        scope=Scope(kind="order", order_id="4821", customer_id="customer-4821", exception_id="exc-4821")))
    assert revised["parent_candidate_id"] == broad["candidate_id"]
    passed = execute(env, revised)
    assert passed["admission"] == "eligible"
    approved = service.decide(revised["candidate_id"], "approve-1", "approve", "safe exact revision", passed["run_id"])
    assert approved["status"] == "approved"
    assert store.active()["parent_version_id"] == initial
    assert store.active()["memories"][0]["text"] == NARROW
    assert service.history()["events"][0]["decision"] == "approve"
    assert len(service.history()["versions"]) == 2
    # A retried reviewer request does not create another version/event.
    assert service.decide(revised["candidate_id"], "approve-1", "approve", "safe exact revision", passed["run_id"]) == approved
    assert store.db.review_events.count_documents(store.query()) == 1


def test_a_b_inputs_are_frozen_and_isolated(env, fake_selection):
    _, store, provider, service, _ = env
    candidate = stage(env, True)
    run_id = service.create_run(candidate["candidate_id"])["run_id"]
    # Change live data after freezing; neither side should observe this mutation.
    store.db.task_fixtures.update_many(store.query(), {"$set": {"task.message": "LIVE MUTATION"}})
    worker = Worker(service)
    run = worker.claim()
    worker.execute(run)
    assert len(provider.calls) == 12
    assert all(task["message"] != "LIVE MUTATION" for task, _ in provider.calls)
    assert sum(len(memories) == 1 for _, memories in provider.calls) == 6
    assert sum(len(memories) == 0 for _, memories in provider.calls) == 6
    assert store.active()["memories"] == []


@pytest.mark.parametrize("failure", ["provider", "budget", "useful"])
def test_error_or_incomplete_evidence_never_eligible(env, fake_selection, failure):
    cfg, store, provider, service, _ = env
    candidate = stage(env, True)
    if failure == "provider":
        provider.fail = True
    elif failure == "budget":
        cfg.max_run_model_calls = 2
    else:
        candidate["scope"] = {"kind": "order", "order_id": "4821", "customer_id": "customer-4821", "exception_id": "exc-4821"}
        original = provider.decide
        def refuse_useful(task, memories, reserve):
            return original(task, [], reserve)
        provider.decide = refuse_useful
    result = execute(env, candidate)
    assert result["admission"] == "inconclusive"
    assert store.active()["memories"] == []
    with pytest.raises(Problem):
        service.decide(candidate["candidate_id"], "bad-approve", "approve", "no", result["run_id"])


@pytest.mark.parametrize("change", ["text", "policy", "base"])
def test_stale_approval_rejected(env, fake_selection, change):
    _, store, provider, service, _ = env
    candidate = stage(env, True)
    run = execute(env, candidate)
    if change == "text":
        store.db.memory_candidates.update_one(store.query(candidate_id=candidate["candidate_id"]), {"$set": {"text": "tampered"}})
    elif change == "policy":
        store.db.trusted_exceptions.update_one(store.query(exception_id="exc-4821"), {"$set": {"amount_cents": 4000}})
    else:
        store.db.workspace_state.update_one(store.query(), {"$set": {"active_memory_version_id": "other"}})
    with pytest.raises(Problem, match="Approval requires"):
        service.decide(candidate["candidate_id"], "stale", "approve", "stale", run["run_id"])


def test_concurrent_approvals_only_one_winner(env, fake_selection):
    _, store, provider, service, _ = env
    first = stage(env, True)
    a = execute(env, first)
    second = stage(env, True)
    b = execute(env, second)
    def approve(args):
        candidate, run, key = args
        try:
            service.decide(candidate["candidate_id"], key, "approve", "parallel", run["run_id"])
            return True
        except Problem:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        wins = list(pool.map(approve, [(first, a, "a"), (second, b, "b")]))
    assert sum(wins) == 1
    assert len(service.history()["versions"]) == 2


def test_interrupted_activation_receipt_recovers(env, fake_selection, monkeypatch):
    _, store, provider, service, _ = env
    candidate = stage(env, True)
    run = execute(env, candidate)
    real = service.reconcile
    calls = []
    def interrupted():
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("simulated process interruption after CAS")
        real()
    monkeypatch.setattr(service, "reconcile", interrupted)
    with pytest.raises(RuntimeError):
        service.decide(candidate["candidate_id"], "crash", "approve", "safe", run["run_id"])
    assert store.active()["candidate_id"] == candidate["candidate_id"]
    assert store.db.workspace_state.find_one(store.query())["pending_receipt"]
    monkeypatch.setattr(service, "reconcile", real)
    real()
    result = service.decide(candidate["candidate_id"], "crash", "approve", "safe", run["run_id"])
    assert result["status"] == "approved"
    assert store.db.review_events.count_documents(store.query()) == 1


def test_quarantine_idempotency_and_revision_preserve_evidence(env):
    _, store, _, service, _ = env
    candidate = stage(env)
    service.decide(candidate["candidate_id"], "q", "quarantine", "manual")
    service.decide(candidate["candidate_id"], "q", "quarantine", "manual")
    with pytest.raises(Problem, match="different request"):
        service.decide(candidate["candidate_id"], "q", "quarantine", "changed reason")
    assert store.active()["memories"] == []


def test_lease_resume_preserves_completed_evidence(env, fake_selection):
    _, store, provider, service, _ = env
    candidate = stage(env, True)
    run_id = service.create_run(candidate["candidate_id"])["run_id"]
    store.settings.max_concurrent_model_calls = 1
    first = Worker(service)
    run = first.claim()
    original = provider.decide
    count = []
    def stop_after_one(task, memories, reserve, deadline=None):
        result = original(task, memories, reserve)
        count.append(1)
        first.stop_event.set()
        return result
    provider.decide = stop_after_one
    first.execute(run)
    assert store.db.case_results.count_documents(store.query(run_id=run_id)) == 1
    store.db.evaluation_runs.update_one(store.query(run_id=run_id), {"$set": {"lease_until": "2000-01-01T00:00:00+00:00"}})
    provider.decide = original
    second = Worker(service)
    second.execute(second.claim())
    assert store.db.case_results.count_documents(store.query(run_id=run_id)) == 12
    assert len(provider.calls) == 12


def test_observed_violation_quarantines_even_with_other_errors(env, fake_selection):
    _, store, provider, service, _ = env
    original = provider.decide
    def partially_failed(task, memories, reserve, deadline=None):
        if task["return_received"]:
            reserve()
            raise RuntimeError("test-only partial outage")
        return original(task, memories, reserve)
    provider.decide = partially_failed
    run = execute(env, stage(env))
    assert run["admission"] == "quarantine"
    assert run["summary"]["errors"] > 0


def test_empty_evidence_cannot_be_approved(env, fake_selection):
    _, store, provider, service, _ = env
    candidate = stage(env, True)
    run = execute(env, candidate)
    store.db.case_results.update_one(store.query(run_id=run["run_id"]), {"$set": {"checks": [], "raw_responses": []}})
    with pytest.raises(Problem, match="twelve safe"):
        service.decide(candidate["candidate_id"], "missing-evidence", "approve", "attempt", run["run_id"])
