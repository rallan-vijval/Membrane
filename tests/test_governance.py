"""Governance rules, checked against the real Atlas cluster. No LLM calls.

Skipped unless RUN_LIVE_INTEGRATION=1 and MONGODB_URI is set. Uses its own tenants (test_a / test_b) and cleans up.
"""
import os
from datetime import timedelta

import pytest

pytest.importorskip("pymongo")
from dotenv import load_dotenv  # noqa: E402

if os.environ.get("RUN_LIVE_INTEGRATION") != "1":
    pytest.skip("Set RUN_LIVE_INTEGRATION=1 to opt into real Atlas tests", allow_module_level=True)

load_dotenv()
if not os.environ.get("MONGODB_URI"):
    pytest.skip("MONGODB_URI not set", allow_module_level=True)

from membrane import memory  # noqa: E402
from membrane.db import get_db, now  # noqa: E402

A, B = "test_a", "test_b"


@pytest.fixture(autouse=True)
def clean():
    db = get_db()
    yield
    for coll in (db.memory_versions, db.simulation_runs, db.sources):
        coll.delete_many({"tenant_id": {"$in": [A, B]}})


def ids(tenant, order=None, view="A", candidate=None):
    mems, _ = memory.get_memories(tenant, "refund without return", order, view, candidate)
    return {m["_id"] for m in mems}


def passing_run(mem_id, verdict="pass"):
    run_id = memory.new_id("run")
    get_db().simulation_runs.insert_one({"_id": run_id, "candidate_id": mem_id, "tenant_id": A,
                                         "verdict": verdict, "created_at": now()})
    return run_id


def staged(scope=None, tenant=A):
    return memory.stage_memory("VIP customers may keep refunded items.", None, tenant,
                               scope or {"kind": "global"})


def test_proposed_memory_never_reaches_the_live_agent():
    mid = staged()
    assert mid not in ids(A)
    assert mid in ids(A, view="B", candidate=mid)       # only the preview sees it
    assert get_db().memory_versions.find_one({"_id": mid})["status"] == "proposed"


def test_accept_requires_a_passing_run():
    mid = staged()
    with pytest.raises(memory.MembraneError):
        memory.accept(mid, passing_run(mid, verdict="fail"), "rev")
    assert mid not in ids(A)


def test_quarantined_memory_cannot_be_accepted():
    mid = staged()
    run_id = passing_run(mid)
    memory.quarantine(mid, "rev", "failed preview", run_id)
    with pytest.raises(memory.MembraneError):
        memory.accept(mid, run_id, "rev")
    assert mid not in ids(A)


def test_order_scope_applies_to_that_order_only():
    mid = staged({"kind": "order", "order_id": "4821"})
    memory.accept(mid, passing_run(mid), "rev")
    assert mid in ids(A, "4821")
    assert mid not in ids(A, "5530")


def test_no_leak_between_tenants():
    mid = staged()
    memory.accept(mid, passing_run(mid), "rev")
    assert mid in ids(A)
    assert mid not in ids(B)
    assert mid not in ids(B, view="B", candidate=mid)   # not even in another tenant's preview


def test_revoked_memory_is_not_retrieved():
    mid = staged()
    memory.accept(mid, passing_run(mid), "rev")
    memory.revoke(mid, "rev", "wrong")
    assert mid not in ids(A)


def test_expired_memory_is_not_retrieved():
    mid = staged()
    memory.accept(mid, passing_run(mid), "rev")
    get_db().memory_versions.update_one({"_id": mid}, {"$set": {"expires_at": now() - timedelta(seconds=1)}})
    assert mid not in ids(A)
    assert memory.effective_status(get_db().memory_versions.find_one({"_id": mid})) == "expired"


def test_correction_supersedes_the_old_version_only_once_accepted():
    old = staged()
    memory.accept(old, passing_run(old), "rev")
    new = memory.revise(old, "Order 4821 may keep the item.", {"kind": "order", "order_id": "4821"}, "rev")
    assert old in ids(A)                                 # still in force while the fix is tested
    assert old not in ids(A, "4821", view="B", candidate=new)
    memory.accept(new, passing_run(new), "rev")
    assert old not in ids(A) and new in ids(A, "4821")
    assert get_db().memory_versions.find_one({"_id": old})["status"] == "superseded"


def test_audit_trail_links_source_runs_and_decisions():
    src = memory.save_source("Order 4821 exception note", A)
    mid = memory.stage_memory("Order 4821 may keep the item.", src, A, {"kind": "order", "order_id": "4821"})
    run_id = passing_run(mid)
    memory.accept(mid, run_id, "rev")
    trail = memory.audit_trail(mid)
    assert trail["source"]["_id"] == src
    assert [r["_id"] for r in trail["runs"]] == [run_id]
    events = [h["event"] for h in trail["memory"]["history"]]
    assert events == ["staged", "accepted"]
    assert trail["memory"]["history"][1]["run_id"] == run_id
