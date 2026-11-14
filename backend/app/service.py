from .suite import SUITE_VERSION, CASE_COUNT, EXECUTION_COUNT
import hashlib
from functools import wraps
from threading import RLock
from datetime import datetime, timedelta, timezone

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from .common import Problem, digest, now, uid
from .models import Candidate, Scope, Source, Version
from .policy import POLICY
from .provider import ARGUMENT_SCHEMA, SYSTEM
from .selection import select
from .integration_bridge import Embeddings, SafeTracing
from .memory_governance import MemoryGovernance, content_hash


def serialized(method):
    """Serialize lifecycle transitions in the single API process; Atlas CAS protects activation."""
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self.lifecycle_lock:
            return method(self, *args, **kwargs)
    return wrapped


class Service:
    def __init__(self, store, provider, embeddings=None, tracer=None):
        self.store, self.provider = store, provider
        self.lifecycle_lock = RLock()
        self.embeddings = embeddings or Embeddings(store.settings, getattr(provider, "_semaphore", None))
        self.tracing = SafeTracing(store.settings, tracer)
        self.memory = MemoryGovernance(self)

    def source(self, data, mime):
        extracted, provenance = self.provider.extract(data, mime)
        source_id = uid("source")
        path = self.store.settings.data_dir / "images" / f"{source_id}.{'png' if mime == 'image/png' else 'jpg'}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        doc = self.store.doc(source_id=source_id, sha256=hashlib.sha256(data).hexdigest(), mime_type=mime,
            image_url=f"/api/sources/{source_id}/image", **extracted, provenance=provenance, trust="untrusted", local_path=str(path))
        self.store.db.sources.insert_one(doc)
        return self.public(Source, doc)

    @staticmethod
    def public(model, doc):
        return model.model_validate({k: v for k, v in doc.items() if k in model.model_fields}).model_dump()

    def stage(self, body, parent=None):
        self.store.get("sources", "source_id", body.source_id)
        active = self.store.active()
        if active["version_id"] != body.base_version_id:
            raise Problem("stale_base", "Active memory changed; refresh before staging")
        scope = body.scope.model_dump()
        doc = self.store.doc(candidate_id=uid("candidate"), source_id=body.source_id, text=body.text,
            scope=scope, parent_candidate_id=parent, base_version_id=body.base_version_id,
            ttl_seconds=body.ttl_seconds, content_hash=content_hash(body.text, scope, body.ttl_seconds), status="staged", latest_run_id=None)
        self.store.db.memory_candidates.insert_one(doc)
        return self.public(Candidate, doc)

    def revise(self, candidate_id, body):
        from .models import CandidateIn
        old = self.store.get("memory_candidates", "candidate_id", candidate_id)
        if old["status"] in ("testing", "approved"):
            raise Problem("invalid_state", "Cannot revise a testing or approved candidate")
        return self.stage(CandidateIn(source_id=old["source_id"], text=body.text, scope=body.scope,
                          ttl_seconds=body.ttl_seconds, base_version_id=self.store.active()["version_id"]), candidate_id)

    def policy_snapshot(self):
        exceptions = list(self.store.db.trusted_exceptions.find(self.store.query(), {"_id": 0, "created_at": 0}))
        exceptions.sort(key=lambda x: x["exception_id"])
        return {"policy": POLICY, "exceptions": exceptions}

    @serialized
    def create_run(self, candidate_id):
        s = self.store
        self.reconcile()
        if s.settings.governed_memory_enabled:
            self.memory.require_enabled()
        candidate = s.get("memory_candidates", "candidate_id", candidate_id)
        if candidate["content_hash"] != content_hash(candidate["text"], candidate["scope"], candidate.get("ttl_seconds", 3600)):
            raise Problem("legacy_candidate", "Create a new revision with lifetime-aware content before testing")
        if candidate["status"] not in ("staged", "eligible", "inconclusive"):
            raise Problem("invalid_state", "Only staged, eligible, or inconclusive candidates may be tested")
        active = s.active()
        if active["version_id"] != candidate["base_version_id"]:
            raise Problem("stale_base", "Create a revision against the current active memory before retesting")
        run_id = uid("run")
        locked = s.db.memory_candidates.update_one(s.query(candidate_id=candidate_id, status=candidate["status"], latest_run_id=candidate.get("latest_run_id")),
            {"$set": {"status": "testing", "latest_run_id": run_id, "testing_since": now()}})
        if locked.modified_count != 1:
            raise Problem("candidate_busy", "Another operation changed this candidate")
        snapshot = self.policy_snapshot()
        run = s.doc(run_id=run_id, candidate_id=candidate_id, status="queued", admission=None, reasons=[],
            progress={"completed": 0, "total": EXECUTION_COUNT}, selection=[], selection_metadata={}, summary={}, usage={}, suite_version=SUITE_VERSION,
            config=self.provider.config(), base_version_id=active["version_id"], candidate_hash=candidate["content_hash"],
            frozen_candidate={"text": candidate["text"], "scope": candidate["scope"], "ttl_seconds": candidate.get("ttl_seconds", 3600)}, frozen_memory=active["memories"],
            policy_snapshot=snapshot, policy_hash=digest(snapshot), tool_schema=ARGUMENT_SCHEMA, system_prompt=SYSTEM,
            model_calls=0, lease_until=None, lease_owner=None, live=True, memory_retrieval=[], governance_version=2 if s.settings.governed_memory_enabled else 1)
        try:
            s.db.evaluation_runs.insert_one(run)
            selection, metadata = select(s, self.provider, candidate, self.embeddings) if s.settings.governed_memory_enabled else select(s, self.provider, candidate)
            retrievals = []
            if s.settings.governed_memory_enabled:
                with self.tracing.span("freeze_memory_retrieval", {"workspace_id": s.workspace, "run_id": run_id}):
                    retrievals = [self.memory.retrieve(case["task"], case["case_id"], active, run["created_at"]) for case in selection]
                metadata["memory_profile_id"] = self.embeddings.describe()["profile_id"]
            if s.active()["version_id"] != active["version_id"]:
                raise Problem("stale_base", "Active memory changed while preparing the suite; retest")
            s.db.evaluation_runs.update_one(s.query(run_id=run_id), {"$set": {"selection": selection, "selection_metadata": metadata,
                "memory_retrieval": retrievals}})
        except Exception as exc:
            message = exc.message if isinstance(exc, Problem) else "Selection or persistence failed"
            s.db.evaluation_runs.update_one(s.query(run_id=run_id), {"$set": {"status": "inconclusive", "admission": "inconclusive", "reasons": [message]}})
            s.db.memory_candidates.update_one(s.query(candidate_id=candidate_id, latest_run_id=run_id), {"$set": {"status": "inconclusive"}})
        return {"run_id": run_id}

    @serialized
    def reconcile(self):
        """A receipt on the authoritative state pointer makes interrupted decisions recoverable."""
        s = self.store
        # Older unfinished suites are not resumed under a different coverage contract.
        for old in s.db.evaluation_runs.find(s.query(suite_version={"$ne": SUITE_VERSION}, status={"$in": ["queued", "running"]})):
            s.db.evaluation_runs.update_one(s.query(run_id=old["run_id"], status=old["status"]),
                {"$set": {"status": "inconclusive", "admission": "inconclusive", "lease_owner": None,
                          "reasons": ["Test suite changed; start a new test"]}})
            s.db.memory_candidates.update_one(s.query(candidate_id=old["candidate_id"], latest_run_id=old["run_id"], status="testing"),
                {"$set": {"status": "inconclusive"}})
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=max(180, s.settings.model_timeout_seconds * 3 + 30))).isoformat()
        # A crash during suite preparation must not leave a candidate testing forever.
        abandoned = list(s.db.evaluation_runs.find(s.query(status="queued", created_at={"$lt": cutoff}, **{"selection.2": {"$exists": False}})))
        for run in abandoned:
            s.db.evaluation_runs.update_one(s.query(run_id=run["run_id"], status="queued", **{"selection.2": {"$exists": False}}),
                {"$set": {"status": "inconclusive", "admission": "inconclusive", "reasons": ["Interrupted during suite preparation; retest required"]}})
            s.db.memory_candidates.update_one(s.query(candidate_id=run["candidate_id"], status="testing", latest_run_id=run["run_id"]),
                                              {"$set": {"status": "inconclusive"}})
        for candidate in s.db.memory_candidates.find(s.query(status="testing", testing_since={"$lt": cutoff})):
            if not s.db.evaluation_runs.find_one(s.query(run_id=candidate.get("latest_run_id"))):
                s.db.memory_candidates.update_one(s.query(candidate_id=candidate["candidate_id"], status="testing", latest_run_id=candidate.get("latest_run_id")),
                                                  {"$set": {"status": "inconclusive"}})
        state = s.get("workspace_state", "workspace_id", s.workspace)
        receipt = state.get("pending_receipt")
        if not receipt:
            return
        if receipt["decision"] != "revoke":
            s.db.memory_candidates.update_one(s.query(candidate_id=receipt["candidate_id"]),
                {"$set": {"status": "approved" if receipt["decision"] == "approve" else "quarantined"}})
        s.db.review_events.update_one(s.query(idempotency_key=receipt["idempotency_key"]), {"$setOnInsert": receipt}, upsert=True)
        s.db.workspace_state.update_one(s.query(revision=state["revision"], **{"pending_receipt.event_id": receipt["event_id"]}),
                                        {"$set": {"pending_receipt": None}})

    @serialized
    def decide(self, candidate_id, key, decision, reason, run_id=None):
        s = self.store
        self.reconcile()
        request_hash = digest({"candidate": candidate_id, "decision": decision, "reason": reason, "run_id": run_id})
        prior = s.db.review_events.find_one(s.query(idempotency_key=key))
        if prior:
            if prior["request_hash"] != request_hash:
                raise Problem("idempotency_conflict", "Idempotency key was used with a different request")
            return self.public(Candidate, s.get("memory_candidates", "candidate_id", candidate_id))
        state = s.get("workspace_state", "workspace_id", s.workspace)
        cand = s.get("memory_candidates", "candidate_id", candidate_id)
        if cand["status"] not in (("eligible",) if decision == "approve" else ("staged", "eligible", "inconclusive")):
            raise Problem("invalid_state", "Candidate is not in a reviewable state")
        version_id = None
        if decision == "approve":
            run = s.get("evaluation_runs", "run_id", run_id)
            if (run["status"] != "completed" or run["admission"] != "eligible" or run["progress"]["completed"] != EXECUTION_COUNT
                or run.get("suite_version") != SUITE_VERSION or len(run["selection"]) != CASE_COUNT
                or run["candidate_id"] != candidate_id or cand["latest_run_id"] != run_id
                or run["candidate_hash"] != cand["content_hash"] or cand["content_hash"] != content_hash(cand["text"], cand["scope"], cand.get("ttl_seconds", 3600))
                or run["policy_hash"] != digest(self.policy_snapshot()) or run["base_version_id"] != state["active_memory_version_id"]):
                raise Problem("stale_evidence", "Approval requires exact current passing candidate, base, and policy evidence")
            if s.settings.governed_memory_enabled:
                self.memory.require_enabled()
                if run.get("governance_version") != 2 or len(run.get("memory_retrieval", [])) != CASE_COUNT:
                    raise Problem("stale_evidence", "Retest using the initialized governed-memory profile")
                if any(r["profile_id"] != self.embeddings.describe()["profile_id"] for r in run["memory_retrieval"]):
                    raise Problem("stale_evidence", "Embedding profile changed; retest")
                self.memory.validate_frozen(run["memory_retrieval"], now())
            # Recheck immutable case evidence rather than trusting a UI or summary.
            results = list(s.db.case_results.find(s.query(run_id=run_id)))
            expected_keys = {(case["case_id"], side, repetition) for case in run["selection"]
                             for side in ("baseline", "candidate") for repetition in (1, 2)}
            actual_keys = {(r["case_id"], r["side"], r["repetition"]) for r in results}
            if (len(results) != EXECUTION_COUNT or actual_keys != expected_keys or any(
                r["error"] or not r["raw_responses"] or not r["attempt"] or not r["checks"]
                or any(not c["passed"] for c in r["checks"]) for r in results)):
                raise Problem("incomplete_evidence", "All twelve safe completed executions are required")
            # An exception may expire after testing even when its document hash is unchanged.
            from .policy import enforce
            cases = {case["case_id"]: case for case in run["selection"]}
            for result in results:
                if result["attempt"]["action"] == "refund_order":
                    current_outcome = enforce(result["attempt"]["arguments"], cases[result["case_id"]]["task"],
                                              run["policy_snapshot"]["exceptions"], now())
                    if not current_outcome["allowed"]:
                        raise Problem("stale_evidence", "Trusted refund authority changed or expired after testing")
            version_id = "version_" + digest({"workspace": s.workspace, "key": key})[:32]
            base = s.get("memory_versions", "version_id", state["active_memory_version_id"])
            if len(base["memories"]) >= 100:
                raise Problem("memory_limit", "Revoke an entry before exceeding the 100-memory demo limit")
            entry = {"text": cand["text"], "scope": cand["scope"], "candidate_id": candidate_id}
            if s.settings.governed_memory_enabled:
                entry = self.memory.prepare_entry(self.memory.make_entry(cand, version_id), cand["ttl_seconds"])
                if datetime.fromisoformat(entry["expires_at"]) <= datetime.now(timezone.utc):
                    raise Problem("stale_evidence", "Prepared memory expired; use a fresh decision key")
            version = s.doc(version_id=version_id, parent_version_id=base["version_id"],
                memories=base["memories"] + [entry],
                candidate_id=candidate_id, run_id=run_id, policy_hash=run["policy_hash"])
            s.db.memory_versions.update_one(s.query(version_id=version_id), {"$setOnInsert": version}, upsert=True)
        receipt = s.doc(event_id="event_" + digest({"workspace": s.workspace, "key": key})[:32], actor="Local demo reviewer",
            decision=decision, candidate_id=candidate_id, run_id=run_id, version_id=version_id, reason=reason,
            idempotency_key=key, request_hash=request_hash)
        changes = {"pending_receipt": receipt}
        if version_id:
            changes["active_memory_version_id"] = version_id
        result = s.db.workspace_state.update_one(s.query(revision=state["revision"], pending_receipt=None),
                                                {"$set": changes, "$inc": {"revision": 1}})
        if result.modified_count != 1:
            self.reconcile()
            prior = s.db.review_events.find_one(s.query(idempotency_key=key))
            if prior and prior["request_hash"] == request_hash:
                return self.public(Candidate, s.get("memory_candidates", "candidate_id", candidate_id))
            raise Problem("concurrent_decision", "Another decision changed workspace state; refresh and retest")
        self.reconcile()
        return self.public(Candidate, s.get("memory_candidates", "candidate_id", candidate_id))

    def memory_entries(self):
        return self.memory.list_entries()

    @serialized
    def revoke(self, memory_id, body, key):
        s = self.store
        self.memory.require_enabled()
        self.reconcile()
        request_hash = digest({"memory_id": memory_id, "base_version_id": body.base_version_id, "reason": body.reason, "decision": "revoke"})
        prior = s.db.review_events.find_one(s.query(idempotency_key=key))
        if prior:
            if prior["request_hash"] != request_hash:
                raise Problem("idempotency_conflict", "Idempotency key belongs to a different decision")
            return {"version_id": prior["version_id"], "event_id": prior["event_id"]}
        state = s.get("workspace_state", "workspace_id", s.workspace)
        base = s.active()
        if body.base_version_id != base["version_id"]:
            raise Problem("stale_base", "Active version changed; refresh before revoking")
        entry = next((e for e in base["memories"] if e.get("memory_id") == memory_id), None)
        if entry is None:
            raise Problem("memory_not_active", "Memory is no longer in the active snapshot")
        version_id = "version_" + digest({"workspace": s.workspace, "key": key, "decision": "revoke"})[:32]
        version = s.doc(version_id=version_id, parent_version_id=base["version_id"],
            memories=[e for e in base["memories"] if e.get("memory_id") != memory_id], candidate_id=None,
            run_id=None, policy_hash=digest(self.policy_snapshot()))
        s.db.memory_versions.update_one(s.query(version_id=version_id), {"$setOnInsert": version}, upsert=True)
        receipt = s.doc(event_id="event_" + digest({"workspace": s.workspace, "key": key})[:32], actor="Local demo reviewer",
            decision="revoke", candidate_id=entry["candidate_id"], run_id=None, version_id=version_id,
            memory_id=memory_id, base_version_id=base["version_id"], reason=body.reason, idempotency_key=key, request_hash=request_hash)
        changed = s.db.workspace_state.update_one(s.query(revision=state["revision"], pending_receipt=None),
            {"$set": {"active_memory_version_id": version_id, "pending_receipt": receipt}, "$inc": {"revision": 1}})
        if changed.modified_count != 1:
            self.reconcile()
            prior = s.db.review_events.find_one(s.query(idempotency_key=key))
            if prior and prior["request_hash"] == request_hash:
                return {"version_id": prior["version_id"], "event_id": prior["event_id"]}
            raise Problem("concurrent_decision", "Workspace changed during revocation; refresh")
        self.reconcile()
        return {"version_id": version_id, "event_id": receipt["event_id"]}

    def tasks(self):
        docs = list(self.store.fixtures.find(self.store.query(split="development", enabled=True),
            {"_id": 0, "fixture_id": 1, "description": 1}).sort("fixture_id", 1).limit(101))
        return {"items": docs[:100], "truncated": len(docs) > 100}

    def execute_active(self, fixture_id, body):
        from .active_execution import execute
        return execute(self, fixture_id, body)

    def active_execution(self, execution_id):
        from .models import ActiveExecution
        return self.public(ActiveExecution, self.store.get("live_executions", "execution_id", execution_id))

    def history(self):
        self.reconcile()
        versions, current = [], self.store.active()
        while current and len(versions) < 100:
            versions.append(self.public(Version, current))
            parent = current["parent_version_id"]
            current = self.store.get("memory_versions", "version_id", parent) if parent else None
        events, truncated = self.store.list("review_events")
        from .models import ReviewEvent
        return {"versions": versions, "events": [self.public(ReviewEvent, x) for x in events], "truncated": truncated or current is not None}
