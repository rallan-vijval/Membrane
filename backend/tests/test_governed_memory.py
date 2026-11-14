"""Agent A's explicit test doubles; no replacement application store/provider exists."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import mongomock
import pytest
from fastapi.testclient import TestClient

from backend.app.common import Problem, now
from backend.app.config import Settings
from backend.app.fixtures import NARROW
from backend.app.main import create_app
from backend.app.memory_governance import MEMORY_COLLECTION, content_hash
from backend.app.models import CandidateIn, ExecuteActiveIn, RevokeIn, Scope
from backend.app.runner import Worker
from backend.app.service import Service
from backend.app.store import Store
from conftest import FakeProvider
from scripts.backend_setup import seed


class FakeEmbeddings:
    def __init__(self):
        self.calls = []
        self.profile_id = "EXPLICIT_TEST_PROFILE"
    def describe(self):
        return {"profile_id": self.profile_id, "provider": "TEST", "model": "test-embedding", "dimensions": 3}
    def embed_query(self, text):
        self.calls.append(("query", text))
        return SimpleNamespace(vectors=[[1, 0, 0]], profile_id=self.profile_id, input_tokens=3, attempted_calls=1, elapsed_ms=1)
    def embed_documents(self, texts):
        self.calls.append(("document", texts))
        return SimpleNamespace(vectors=[[1, 0, 0] for _ in texts], profile_id=self.profile_id, input_tokens=3, attempted_calls=1, elapsed_ms=1)


@pytest.fixture
def governed(tmp_path, monkeypatch):
    cfg = Settings(_env_file=None, governed_memory_enabled=True, workspace_id="test-v2", worker_enabled=False,
                   embedding_model="test-embedding", embedding_dimensions=3, data_dir=tmp_path)
    store = Store(cfg, mongomock.MongoClient().db)
    seed(store)
    provider, embeddings = FakeProvider(cfg), FakeEmbeddings()
    service = Service(store, provider, embeddings)
    monkeypatch.setattr(service.memory, "ensure_index", lambda: None)
    for doc in store.fixtures.find(store.query()):
        store.fixtures.update_one({"_id": doc["_id"]}, {"$set": {"embedding": [1, 0, 0], "embedding_model": "test-embedding", "profile_id": embeddings.profile_id}})
    def fixtures_search(pipeline):
        return [{**d, "semantic_score": 0.9} for d in store.fixtures.find(store.query(split="development"), {"_id": 0}).sort("fixture_id", 1).limit(4)]
    def memory_search(pipeline):
        filt = pipeline[0]["$vectorSearch"]["filter"]
        assert filt["workspace_id"] == store.workspace
        assert filt["scope.kind"] == {"$in": ["global", "preference"]}
        return [{**d, "semantic_score": 0.9} for d in store.db[MEMORY_COLLECTION].find(filt, {"_id": 0}).limit(6)]
    monkeypatch.setattr(store.fixtures, "aggregate", fixtures_search)
    monkeypatch.setattr(store.db[MEMORY_COLLECTION], "aggregate", memory_search)
    source = service.source(b"TEST_ONLY", "image/png")
    return cfg, store, provider, embeddings, service, source


def stage(governed, text=NARROW, scope=None, ttl=3600):
    cfg, store, provider, embeddings, service, source = governed
    scope = scope or Scope(kind="order", order_id="4821", customer_id="customer-4821", exception_id="exc-4821")
    return service.stage(CandidateIn(source_id=source["source_id"], text=text, scope=scope,
        base_version_id=store.active()["version_id"], ttl_seconds=ttl))


def evaluate(governed, candidate):
    cfg, store, provider, embeddings, service, source = governed
    run_id = service.create_run(candidate["candidate_id"])["run_id"]
    worker = Worker(service)
    claimed = worker.claim()
    assert claimed is not None, store.get("evaluation_runs", "run_id", run_id)
    worker.execute(claimed)
    return worker.detail(run_id)


def admit(governed):
    service = governed[4]
    candidate = stage(governed)
    run = evaluate(governed, candidate)
    assert run["admission"] == "eligible"
    service.decide(candidate["candidate_id"], "approve:" + candidate["candidate_id"], "approve", "tested", run["run_id"])
    return service.memory_entries()["items"][-1]


def test_active_memory_before_approval_after_approval_after_revoke_and_reload(governed):
    cfg, store, provider, embeddings, service, _ = governed
    before = service.execute_active("development-01", ExecuteActiveIn(base_version_id=store.active()["version_id"]))
    assert before["execution"]["attempt"]["action"] == "request_return"
    assert before["retrieval"]["entries"] == []
    entry = admit(governed)
    approved_version = store.active()["version_id"]
    after = service.execute_active("development-01", ExecuteActiveIn(base_version_id=approved_version))
    assert after["execution"]["attempt"]["action"] == "refund_order"
    assert after["execution"]["tool_outcome"]["allowed"]
    assert after["retrieval"]["entries"][0]["memory_id"] == entry["memory_id"]
    assert after["retrieval"]["entries"][0]["reason"] == "exact_scope"
    assert service.active_execution(after["execution_id"]) == after
    assert store.db.live_executions.find_one(store.query(execution_id=after["execution_id"]))["admission_evidence"] is False
    neighbor = service.execute_active("development-02", ExecuteActiveIn(base_version_id=approved_version))
    assert neighbor["execution"]["attempt"]["action"] == "request_return"
    assert neighbor["retrieval"]["entries"] == []
    result = service.revoke(entry["memory_id"], RevokeIn(base_version_id=approved_version, reason="remove"), "revoke-1")
    again = service.revoke(entry["memory_id"], RevokeIn(base_version_id=approved_version, reason="remove"), "revoke-1")
    assert result == again
    assert store.active()["memories"] == []
    assert store.get("memory_versions", "version_id", approved_version)["memories"][0]["memory_id"] == entry["memory_id"]
    assert store.get("memory_candidates", "candidate_id", entry["candidate_id"])["status"] == "approved"
    after_revoke = service.execute_active("development-01", ExecuteActiveIn(base_version_id=result["version_id"]))
    assert after_revoke["execution"]["attempt"]["action"] == "request_return"
    assert service.history()["events"][0]["decision"] == "revoke"


def test_candidate_ttl_changes_hash_and_is_bounded(governed):
    first, second = stage(governed, ttl=60), stage(governed, ttl=120)
    assert first["content_hash"] != second["content_hash"]
    for bad in (True, 0, 59, 86401, 60.0):
        with pytest.raises(ValueError):
            CandidateIn(source_id="s", text="x", scope=Scope(), base_version_id="v", ttl_seconds=bad)


@pytest.mark.parametrize("scope", [dict(kind="order", order_id="4821"), dict(kind="global", exception_id="invented"),
                                   dict(kind="preference", customer_id="other")])
def test_scope_must_not_claim_incomplete_or_global_authority(scope):
    with pytest.raises(ValueError):
        Scope(**scope)


def test_expiry_boundary_excludes_memory_and_prevents_stale_approval(governed, monkeypatch):
    cfg, store, provider, embeddings, service, _ = governed
    entry = admit(governed)
    active = store.active()
    task = store.get(cfg.fixture_collection, "fixture_id", "development-01")["task"]
    retrieval = service.memory.retrieve(task, "case", active, entry["expires_at"])
    assert retrieval["entries"] == []
    assert service.memory.entries(active, entry["expires_at"])[0]["availability"] == "expired"
    candidate = stage(governed, text="Benign preference", scope=Scope(kind="preference"))
    run = evaluate(governed, candidate)
    assert run["admission"] == "eligible"
    expired_at = (datetime.fromisoformat(entry["expires_at"]) + timedelta(seconds=1)).isoformat()
    monkeypatch.setattr("backend.app.service.now", lambda: expired_at)
    with pytest.raises(Problem, match="expired"):
        service.decide(candidate["candidate_id"], "stale-expiry", "approve", "no", run["run_id"])


def test_frozen_retrieval_same_base_both_sides_and_repetitions(governed):
    cfg, store, provider, embeddings, service, _ = governed
    entry = admit(governed)
    candidate = stage(governed, text="A harmless preference", scope=Scope(kind="preference"))
    run_id = service.create_run(candidate["candidate_id"])["run_id"]
    frozen = store.get("evaluation_runs", "run_id", run_id)
    assert len(frozen["memory_retrieval"]) == 12
    provider.calls.clear()
    # Later changes cannot change the frozen overlay inputs.
    store.db[MEMORY_COLLECTION].update_one(store.query(memory_id=entry["memory_id"]), {"$set": {"text": "LIVE MUTATION"}})
    worker = Worker(service)
    worker.execute(worker.claim())
    assert len(provider.calls) == 48
    assert all(all(m["text"] != "LIVE MUTATION" for m in memories) for _, memories in provider.calls)
    scoped_calls = [memories for task, memories in provider.calls if task["order_id"] == "4821"]
    assert len(scoped_calls) == 4
    assert sum(len(m) == 1 for m in scoped_calls) == 2
    assert sum(len(m) == 2 for m in scoped_calls) == 2


@pytest.mark.parametrize("failure", ["workspace", "scope", "content", "profile", "search"])
def test_memory_search_boundary_and_failure_never_falls_back(governed, monkeypatch, failure):
    cfg, store, provider, embeddings, service, _ = governed
    entry = admit(governed)
    active = store.active()
    task = store.get(cfg.fixture_collection, "fixture_id", "development-01")["task"]
    if failure in ("workspace", "scope"):
        altered = {**entry, "workspace_id": "other" if failure == "workspace" else store.workspace, "semantic_score": 0.9}
        monkeypatch.setattr(store.db[MEMORY_COLLECTION], "aggregate", lambda p: [altered])
    elif failure == "content":
        store.db[MEMORY_COLLECTION].update_one(store.query(memory_id=entry["memory_id"]), {"$set": {"text": "TAMPERED"}})
    elif failure == "profile":
        embeddings.profile_id = "CHANGED"
    else:
        def unavailable(pipeline):
            raise RuntimeError("Synthetic search outage")
        monkeypatch.setattr(store.db[MEMORY_COLLECTION], "aggregate", unavailable)
    with pytest.raises(Problem):
        service.memory.retrieve(task, "case", active, now())


def test_revocation_stales_old_run_and_repeated_new_key_rejects(governed):
    cfg, store, provider, embeddings, service, _ = governed
    entry = admit(governed)
    candidate = stage(governed, text="Preference", scope=Scope(kind="preference"))
    run = evaluate(governed, candidate)
    old_base = store.active()["version_id"]
    service.revoke(entry["memory_id"], RevokeIn(base_version_id=old_base, reason="remove"), "remove")
    with pytest.raises(Problem):
        service.decide(candidate["candidate_id"], "stale", "approve", "no", run["run_id"])
    with pytest.raises(Problem):
        service.revoke(entry["memory_id"], RevokeIn(base_version_id=store.active()["version_id"], reason="again"), "new-key")


def test_active_execution_rejects_heldout_and_stale_base(governed):
    cfg, store, provider, embeddings, service, _ = governed
    with pytest.raises(Problem):
        service.execute_active("heldout-00", ExecuteActiveIn(base_version_id=store.active()["version_id"]))
    with pytest.raises(Problem):
        service.execute_active("development-01", ExecuteActiveIn(base_version_id="stale"))
    assert len(service.tasks()["items"]) == 24
    assert all(t["fixture_id"].startswith("development") for t in service.tasks()["items"])


def test_tracing_failure_never_reexecutes_or_blocks_evidence(governed):
    cfg, store, provider, embeddings, service, _ = governed
    class BrokenContext:
        def __enter__(self):
            raise RuntimeError("Trace transport failed")
        def __exit__(self, *args):
            raise RuntimeError("Trace flush failed")
    class BrokenTracer:
        def span(self, *args):
            return BrokenContext()
    service.tracing.tracer = BrokenTracer()
    candidate = stage(governed)
    run = evaluate(governed, candidate)
    assert run["admission"] == "eligible"
    assert len(provider.calls) == 48


def test_governance_http_shapes_and_revoke_header(governed, monkeypatch):
    cfg, store, provider, embeddings, service, _ = governed
    app = create_app(cfg, store, provider, embeddings)
    monkeypatch.setattr(app.state.service.memory, "ensure_index", lambda: None)
    entry = admit(governed)
    with TestClient(app) as client:
        response = client.get("/api/memory/entries")
        assert response.status_code == 200 and response.json()["items"][0]["availability"] == "active"
        assert client.get("/api/tasks").json()["truncated"] is False
        path = f"/api/memory/entries/{entry['memory_id']}/revoke"
        body = {"base_version_id": store.active()["version_id"], "reason": "remove"}
        assert client.post(path, json=body).status_code == 422
        result = client.post(path, json=body, headers={"Idempotency-Key": "http-revoke"})
        assert result.status_code == 200 and result.json()["event_id"]


def test_scoped_memory_always_included_beside_global_semantic_top_k(governed):
    cfg, store, provider, embeddings, service, _ = governed
    exact = admit(governed)
    base = store.active()
    additions = []
    for i in range(8):
        candidate = stage(governed, text=f"Benign preference {i}", scope=Scope(kind="preference"))
        entry = service.memory.prepare_entry(service.memory.make_entry(candidate, "test_prepared"), 3600)
        additions.append(entry)
    # Explicit domain fixture: publish a synthetic snapshot to test retrieval composition alone.
    version = {**base, "version_id": "test_retrieval_snapshot", "memories": base["memories"] + additions}
    task = store.get(cfg.fixture_collection, "fixture_id", "development-01")["task"]
    retrieval = service.memory.retrieve(task, "case", version, now())
    assert len(retrieval["entries"]) == 7
    assert exact["memory_id"] in [e["memory_id"] for e in retrieval["entries"]]
    assert sum(e["reason"] == "semantic" for e in retrieval["entries"]) == 6
    assert [e["memory_id"] for e in retrieval["entries"]] == [e["memory_id"] for e in sorted(retrieval["entries"], key=lambda e: (e["activated_at"], e["memory_id"]))]


def test_different_customer_cannot_receive_order_memory(governed):
    cfg, store, provider, embeddings, service, _ = governed
    admit(governed)
    task = store.get(cfg.fixture_collection, "fixture_id", "development-01")["task"]
    task["customer_id"] = "different_customer"
    assert service.memory.retrieve(task, "case", store.active(), now())["entries"] == []
    with pytest.raises(Problem, match="workspace"):
        store.query(workspace_id="another_workspace")


def test_revocation_crash_receipt_recovers_without_erasing_candidate(governed, monkeypatch):
    cfg, store, provider, embeddings, service, _ = governed
    entry = admit(governed)
    base = store.active()["version_id"]
    actual = service.reconcile
    calls = []
    def interrupted():
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("Synthetic crash after pointer CAS")
        actual()
    monkeypatch.setattr(service, "reconcile", interrupted)
    body = RevokeIn(base_version_id=base, reason="remove")
    with pytest.raises(RuntimeError):
        service.revoke(entry["memory_id"], body, "crash-revoke")
    assert store.active()["memories"] == []
    monkeypatch.setattr(service, "reconcile", actual)
    result = service.revoke(entry["memory_id"], body, "crash-revoke")
    assert result["event_id"]
    assert store.db.review_events.count_documents(store.query(decision="revoke")) == 1
    assert store.get("memory_candidates", "candidate_id", entry["candidate_id"])["status"] == "approved"


def test_revocation_during_generation_denies_tool_and_keeps_attempt(governed):
    cfg, store, provider, embeddings, service, _ = governed
    entry = admit(governed)
    base = store.active()["version_id"]
    original = provider.decide
    def revoke_while_running(task, memories, reserve):
        result = original(task, memories, reserve)
        service.revoke(entry["memory_id"], RevokeIn(base_version_id=base, reason="concurrent removal"), "during-task")
        return result
    provider.decide = revoke_while_running
    result = service.execute_active("development-01", ExecuteActiveIn(base_version_id=base))
    assert result["execution"]["attempt"]["action"] == "refund_order"
    assert result["execution"]["error"] == "active_authority_changed"
    assert result["execution"]["tool_outcome"]["allowed"] is False
    assert result["execution"]["raw_responses"]


def test_index_unavailable_even_with_empty_active_snapshot_is_not_success(governed, monkeypatch):
    cfg, store, provider, embeddings, service, _ = governed
    from backend.app.memory_governance import MemoryGovernance
    monkeypatch.setattr(service.memory, "ensure_index", lambda: MemoryGovernance.ensure_index(service.memory))
    monkeypatch.setattr(store.db[MEMORY_COLLECTION], "list_search_indexes", lambda name: [])
    candidate = stage(governed)
    run_id = service.create_run(candidate["candidate_id"])["run_id"]
    assert store.get("evaluation_runs", "run_id", run_id)["admission"] == "inconclusive"
    assert provider.calls == []


def test_wording_change_alone_is_not_intended_behavior_change():
    from backend.app.policy import classify
    results = [{"side": side, "repetition": rep, "error": None, "checks": [{"code": "safe", "passed": True}],
                "attempt": {"action": "request_return", "answer": f"Different wording {side} {rep}", "arguments": None}}
               for side in ("baseline", "candidate") for rep in (1, 2)]
    assert classify(results) == "unchanged-safe"
