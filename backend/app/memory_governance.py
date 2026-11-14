"""Authoritative memory membership with scoped semantic retrieval and immutable evidence."""
from datetime import datetime, timedelta

from .common import Problem, digest, now
from .models import MemoryEntry, MemoryRetrieval

MEMORY_COLLECTION = "memory_entries_v2"
MEMORY_INDEX = "memory_semantic_v1"


def content_hash(text, scope, ttl_seconds=3600):
    return digest({"text": text, "scope": scope, "ttl_seconds": ttl_seconds})


def index_definition(dimensions):
    return {"fields": [{"type": "vector", "path": "embedding", "numDimensions": dimensions, "similarity": "cosine"},
        *[{"type": "filter", "path": key} for key in ("workspace_id", "memory_id", "scope.kind")]]}


def batch_value(batch, key, default=None):
    return batch.get(key, default) if isinstance(batch, dict) else getattr(batch, key, default)


def batch_usage(batch):
    return {key: batch_value(batch, key) for key in ("input_tokens", "attempted_calls", "elapsed_ms")}


class MemoryGovernance:
    def __init__(self, service):
        self.service, self.store = service, service.store

    def require_enabled(self):
        if not self.store.settings.governed_memory_enabled:
            raise Problem("governance_disabled", "Enable GOVERNED_MEMORY_ENABLED and seed the v2 workspace", 503)
        state = self.store.get("workspace_state", "workspace_id", self.store.workspace)
        if state.get("governance_version") != 2:
            raise Problem("governance_uninitialized", "Initialize a separate v2 workspace; v1 records will not be rewritten", 503)

    def ensure_index(self):
        try:
            indexes = list(self.store.db[MEMORY_COLLECTION].list_search_indexes(MEMORY_INDEX))
        except Exception:
            raise Problem("memory_search_unavailable", "Memory Search inspection failed", 503)
        expected = index_definition(self.store.settings.embedding_dimensions)
        if not indexes or not indexes[0].get("queryable") or indexes[0].get("latestDefinition") != expected:
            raise Problem("memory_search_unavailable", "Memory Search is not queryable with the configured dimensions/filters", 503)

    def entries(self, version, at):
        if len(version["memories"]) > 100:
            raise Problem("memory_limit", "Demo memory snapshot exceeds the 100-entry limit")
        result = []
        for item in version["memories"]:
            try:
                entry = self.service.public(MemoryEntry, item)
                expired = datetime.fromisoformat(entry["expires_at"]) <= datetime.fromisoformat(at)
            except (ValueError, KeyError, TypeError):
                raise Problem("legacy_memory", "Snapshot lacks governed-memory metadata; use an initialized v2 workspace", 503)
            result.append({**entry, "availability": "expired" if expired else "active"})
        return result

    def list_entries(self):
        self.require_enabled()
        self.service.reconcile()
        version, at = self.store.active(), now()
        return {"version_id": version["version_id"], "evaluated_at": at,
                "items": self.entries(version, at), "truncated": False}

    def make_entry(self, candidate, version_id):
        at = now()
        expiry = (datetime.fromisoformat(at) + timedelta(seconds=candidate["ttl_seconds"])).isoformat()
        return {"memory_id": "memory_" + digest({"workspace": self.store.workspace, "candidate": candidate["candidate_id"]})[:32],
            "text": candidate["text"], "content_hash": candidate["content_hash"], "scope": candidate["scope"],
            "candidate_id": candidate["candidate_id"], "version_id": version_id, "activated_at": at, "expires_at": expiry}

    def prepare_entry(self, entry, ttl_seconds):
        profile = self.service.embeddings.describe()
        existing = self.store.db[MEMORY_COLLECTION].find_one(self.store.query(memory_id=entry["memory_id"]))
        if existing:
            if existing["content_hash"] != entry["content_hash"] or existing.get("profile_id") != profile["profile_id"]:
                raise Problem("memory_profile_mismatch", "Prepared memory uses different content or embedding profile")
            return self.service.public(MemoryEntry, existing)
        batch = self.service.embeddings.embed_documents([entry["text"]])
        vectors = batch_value(batch, "vectors", [])
        if len(vectors) != 1 or len(vectors[0]) != self.store.settings.embedding_dimensions or batch_value(batch, "profile_id") != profile["profile_id"]:
            raise Problem("dimension_mismatch", "Prepared memory embedding profile or length differs", 503)
        entry["activated_at"] = now()
        entry["expires_at"] = (datetime.fromisoformat(entry["activated_at"]) + timedelta(seconds=ttl_seconds)).isoformat()
        self.store.db[MEMORY_COLLECTION].update_one(self.store.query(memory_id=entry["memory_id"]), {"$setOnInsert": self.store.doc(
            **entry, ttl_seconds=ttl_seconds, profile_id=profile["profile_id"], embedding=vectors[0], embedding_usage=batch_usage(batch))}, upsert=True)
        return entry

    def retrieve(self, task, case_id, version, at):
        self.require_enabled()
        self.ensure_index()
        profile = self.service.embeddings.describe()
        eligible = {e["memory_id"]: e for e in self.entries(version, at) if e["availability"] == "active"}
        evidence = {"case_id": case_id, "retrieval_at": at, "profile_id": profile["profile_id"],
                    "base_version_id": version["version_id"], "entries": [], "usage": {}}
        if not eligible:
            return MemoryRetrieval.model_validate(evidence).model_dump()
        query = self.store.query(memory_id={"$in": sorted(eligible)})
        scoped = list(self.store.db[MEMORY_COLLECTION].find({**query, "scope.kind": "order",
            "scope.order_id": task["order_id"], "scope.customer_id": task["customer_id"]}, {"_id": 0}))
        batch = self.service.embeddings.embed_query(task["message"])
        vectors = batch_value(batch, "vectors", [])
        if len(vectors) != 1 or len(vectors[0]) != self.store.settings.embedding_dimensions or batch_value(batch, "profile_id") != profile["profile_id"]:
            raise Problem("dimension_mismatch", "Memory query embedding has a different profile or dimension", 503)
        try:
            semantic = list(self.store.db[MEMORY_COLLECTION].aggregate([
                {"$vectorSearch": {"index": MEMORY_INDEX, "path": "embedding", "queryVector": vectors[0],
                    "numCandidates": 100, "limit": 6, "filter": {**query, "scope.kind": {"$in": ["global", "preference"]}}}},
                {"$set": {"semantic_score": {"$meta": "vectorSearchScore"}}}, {"$project": {"_id": 0}}]))
        except Exception:
            raise Problem("memory_search_unavailable", "Memory Vector Search failed; no keyword/full-snapshot fallback", 503)
        selected = {}
        for found, reason in [(d, "exact_scope") for d in scoped] + [(d, "semantic") for d in semantic]:
            memory_id = found.get("memory_id")
            if memory_id not in eligible or found.get("workspace_id") != self.store.workspace:
                raise Problem("memory_boundary_violation", "Search returned memory outside authoritative membership/workspace")
            # Search can lag. Re-read the immutable document and validate membership/content/expiry/scope.
            current = self.store.get(MEMORY_COLLECTION, "memory_id", memory_id)
            snapshot = eligible[memory_id]
            if (current.get("profile_id") != profile["profile_id"] or current["content_hash"] != snapshot["content_hash"]
                or current["content_hash"] != content_hash(current["text"], current["scope"], current["ttl_seconds"])
                or any(current.get(k) != snapshot.get(k) for k in ("text", "scope", "expires_at", "candidate_id", "version_id"))):
                raise Problem("memory_evidence_mismatch", "Memory document differs from frozen version or embedding profile")
            if datetime.fromisoformat(current["expires_at"]) <= datetime.fromisoformat(at):
                raise Problem("memory_expired", "Search returned an expired memory")
            scope = current["scope"]
            if reason == "semantic" and scope["kind"] not in ("global", "preference"):
                raise Problem("memory_boundary_violation", "Semantic retrieval returned order-scoped memory")
            if scope["kind"] == "order" and (scope["order_id"] != task["order_id"] or scope["customer_id"] != task["customer_id"]):
                raise Problem("memory_boundary_violation", "Exact memory does not match order and customer")
            selected[memory_id] = {**self.service.public(MemoryEntry, current), "reason": reason,
                                   "semantic_score": found.get("semantic_score") if reason == "semantic" else None}
        evidence["entries"] = sorted(selected.values(), key=lambda e: (e["activated_at"], e["memory_id"]))
        evidence["usage"] = batch_usage(batch)
        return MemoryRetrieval.model_validate(evidence).model_dump()

    def validate_frozen(self, retrievals, at):
        for retrieval in retrievals:
            for entry in retrieval["entries"]:
                if datetime.fromisoformat(entry["expires_at"]) <= datetime.fromisoformat(at):
                    raise Problem("stale_evidence", "A retrieved base memory expired after testing; retest")
