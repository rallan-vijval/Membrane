"""Memory lifecycle and governed retrieval.

Statuses:  proposed -> active | quarantined ;  active -> revoked | superseded
Only `active`, unexpired, in-tenant, in-scope memories ever reach the live agent.
Memories are never overwritten: a correction is a new version that supersedes the old one.
"""
from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from .db import get_db, now

log = logging.getLogger("membrane.memory")

MEMORY_INDEX = "memory_vec"
DEFAULT_TTL_DAYS = 30
INDEX_LAG_SECONDS = 120


class MembraneError(Exception):
    """A governance rule refused the operation."""


# --------------------------------------------------------------------------- helpers

def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def in_scope(mem: dict, order_id: str | None) -> bool:
    scope = mem.get("scope") or {}
    return scope.get("kind") == "global" or (
        scope.get("kind") == "order" and scope.get("order_id") == order_id
    )


def validate_scope(scope: dict) -> dict:
    if not isinstance(scope, dict) or scope.get("kind") not in ("global", "order"):
        raise MembraneError('scope must be {"kind": "global"} or {"kind": "order", "order_id": "..."}')
    if scope["kind"] == "order":
        if not scope.get("order_id"):
            raise MembraneError("an order scope needs an order_id")
        return {"kind": "order", "order_id": str(scope["order_id"])}
    return {"kind": "global"}


def _log(mem_id: str, event: str, by: str, **extra) -> None:
    get_db().memory_versions.update_one(
        {"_id": mem_id},
        {"$push": {"history": {"at": now(), "event": event, "by": by, **extra}}},
    )


def _live_filter(tenant_id: str, at) -> dict:
    """The governance rule every retrieval must satisfy."""
    return {"tenant_id": tenant_id, "status": "active", "expires_at": {"$gt": at}}


# --------------------------------------------------------------------------- staging

def save_source(raw_text: str, tenant_id: str, submitted_by: str = "reviewer",
                kind: str = "text", file_name: str | None = None) -> str:
    doc = {
        "_id": new_id("src"), "tenant_id": tenant_id, "kind": kind, "raw_text": raw_text,
        "file_name": file_name, "submitted_by": submitted_by, "synthetic": True,
        "created_at": now(),
    }
    get_db().sources.insert_one(doc)
    return doc["_id"]


def stage_memory(text: str, source_id: str | None, tenant_id: str, scope: dict,
                 supersedes: str | None = None, version: int = 1,
                 proposed_by: str = "agent:support-bot",
                 ttl_days: int = DEFAULT_TTL_DAYS) -> str:
    """Store a candidate as `proposed`. It is NOT visible to the live agent."""
    text = (text or "").strip()
    if not text:
        raise MembraneError("memory text is empty")
    t = now()
    doc = {
        "_id": new_id("mem"),
        "tenant_id": tenant_id,
        "text": text,
        "scope": validate_scope(scope),
        "status": "proposed",
        "version": version,
        "supersedes": supersedes,
        "source_id": source_id,
        "owner": proposed_by,
        "approved_by": None,
        "expires_at": t + timedelta(days=ttl_days),
        "created_at": t,
        "history": [{"at": t, "event": "staged", "by": proposed_by}],
    }
    get_db().memory_versions.insert_one(doc)
    return doc["_id"]


# --------------------------------------------------------------------------- retrieval

def get_memories(tenant_id: str, query_text: str, order_id: str | None, view: str = "A",
                 candidate_id: str | None = None, k: int = 6) -> tuple[list[dict], str]:
    """Memories the agent may use for one task.

    view "A": current memory only (what the live agent sees).
    view "B": the same, plus the candidate -- added directly, never activated.

    Returns (memories, retrieval_mode). retrieval_mode is "vector" or "fallback".

    Global memories are ranked by Atlas Vector Search, with the governance rule applied twice:
    as a pre-filter inside $vectorSearch, and again as a $match on the live document. The search
    index is eventually consistent, so the $match guarantees a memory revoked a second ago is
    never served. Order-scoped memories are fetched by exact key, not by similarity.
    """
    db = get_db()
    at = now()
    live = _live_filter(tenant_id, at)
    global_live = {**live, "scope.kind": "global"}
    mode = "vector"
    try:
        globals_ = list(db.memory_versions.aggregate([
            {"$vectorSearch": {
                "index": MEMORY_INDEX, "path": "text", "query": {"text": query_text},
                "numCandidates": 50, "limit": k,
                "filter": {"$and": [{"tenant_id": tenant_id}, {"status": "active"},
                                    {"expires_at": {"$gt": at}}, {"scope.kind": "global"}]},
            }},
            {"$match": global_live},
        ]))
    except Exception as exc:  # index missing / still building
        log.warning("vector search unavailable, using governed find(): %s", exc)
        globals_ = []
    if not globals_:
        mode = "fallback"
        globals_ = list(db.memory_versions.find(global_live).sort("created_at", 1).limit(k))
    else:
        # Index-lag guard: a memory accepted seconds ago may not be embedded yet.
        seen = {m["_id"] for m in globals_}
        fresh = db.memory_versions.find(
            {**global_live, "activated_at": {"$gt": at - timedelta(seconds=INDEX_LAG_SECONDS)}})
        globals_ += [m for m in fresh if m["_id"] not in seen]

    scoped = []
    if order_id:
        scoped = list(db.memory_versions.find(
            {**live, "scope.kind": "order", "scope.order_id": order_id}))

    # Stable order: oldest first, so View B is exactly View A plus the candidate at the end.
    mems = sorted(globals_ + scoped, key=lambda m: (m["created_at"], m["_id"]))

    if view == "B" and candidate_id:
        cand = db.memory_versions.find_one({"_id": candidate_id})
        if cand and cand["tenant_id"] == tenant_id and in_scope(cand, order_id):
            if cand.get("supersedes"):  # a correction replaces the version it supersedes
                mems = [m for m in mems if m["_id"] != cand["supersedes"]]
            mems.append(cand)
    return mems, mode


# --------------------------------------------------------------------------- decisions

def accept(mem_id: str, run_id: str, reviewer: str, ttl_seconds: int | None = None) -> dict:
    """Activate a candidate. Requires its most recent test run to have passed."""
    db = get_db()
    mem = db.memory_versions.find_one({"_id": mem_id})
    if not mem:
        raise MembraneError("memory not found")
    if mem["status"] != "proposed":
        raise MembraneError(f"only a proposed memory can be accepted (this one is {mem['status']})")
    run = db.simulation_runs.find_one({"_id": run_id})
    if not run or run.get("candidate_id") != mem_id:
        raise MembraneError("that test run does not belong to this memory")
    latest = db.simulation_runs.find_one({"candidate_id": mem_id}, sort=[("created_at", -1)])
    if latest["_id"] != run_id:
        raise MembraneError("a newer test run exists for this memory; use the latest one")
    if run.get("verdict") != "pass":
        raise MembraneError(f"test run verdict is '{run.get('verdict')}', not 'pass'")

    t = now()
    update = {"status": "active", "approved_by": reviewer, "activated_at": t}
    if ttl_seconds:
        update["expires_at"] = t + timedelta(seconds=int(ttl_seconds))
    res = db.memory_versions.update_one({"_id": mem_id, "status": "proposed"}, {"$set": update})
    if res.modified_count != 1:
        raise MembraneError("memory changed state while being accepted")
    _log(mem_id, "accepted", reviewer, run_id=run_id)

    if mem.get("supersedes"):
        old = db.memory_versions.update_one(
            {"_id": mem["supersedes"], "status": "active"}, {"$set": {"status": "superseded"}})
        if old.modified_count:
            _log(mem["supersedes"], "superseded", reviewer, by_memory=mem_id)
    db.simulation_runs.update_one(
        {"_id": run_id}, {"$set": {"decision": "accept", "decided_by": reviewer, "decided_at": t}})
    return db.memory_versions.find_one({"_id": mem_id})


def quarantine(mem_id: str, reviewer: str, reason: str, run_id: str | None = None) -> dict:
    db = get_db()
    res = db.memory_versions.update_one(
        {"_id": mem_id, "status": "proposed"}, {"$set": {"status": "quarantined"}})
    if res.modified_count != 1:
        raise MembraneError("only a proposed memory can be quarantined")
    _log(mem_id, "quarantined", reviewer, reason=reason, run_id=run_id)
    if run_id:
        db.simulation_runs.update_one(
            {"_id": run_id, "candidate_id": mem_id},
            {"$set": {"decision": "quarantine", "decided_by": reviewer, "decided_at": now()}})
    return db.memory_versions.find_one({"_id": mem_id})


def revise(mem_id: str, new_text: str, new_scope: dict, reviewer: str) -> str:
    """Create the next version. It is staged as `proposed` and must pass its own test run.

    Revising a proposed memory quarantines the old version. Revising an ACTIVE memory (a
    correction) leaves the old version in force until the new one is accepted.
    """
    db = get_db()
    old = db.memory_versions.find_one({"_id": mem_id})
    if not old:
        raise MembraneError("memory not found")
    if old["status"] not in ("proposed", "quarantined", "active"):
        raise MembraneError(f"a {old['status']} memory cannot be revised")
    if old["status"] == "proposed":
        quarantine(mem_id, reviewer, "replaced by a revised version")
    new_id_ = stage_memory(new_text, old.get("source_id"), old["tenant_id"], new_scope,
                           supersedes=mem_id, version=old["version"] + 1,
                           proposed_by=f"reviewer:{reviewer}")
    _log(mem_id, "revised", reviewer, new_version=new_id_)
    return new_id_


def revoke(mem_id: str, reviewer: str, reason: str) -> dict:
    """Forget an active memory. It stays in the audit trail but is never retrieved again."""
    db = get_db()
    res = db.memory_versions.update_one(
        {"_id": mem_id, "status": "active"}, {"$set": {"status": "revoked", "revoked_at": now()}})
    if res.modified_count != 1:
        raise MembraneError("only an active memory can be revoked")
    _log(mem_id, "revoked", reviewer, reason=reason)
    return db.memory_versions.find_one({"_id": mem_id})


# --------------------------------------------------------------------------- audit

def effective_status(mem: dict) -> str:
    if mem["status"] == "active" and mem["expires_at"] <= now():
        return "expired"
    return mem["status"]


def list_memories(tenant_id: str | None = None) -> list[dict]:
    q = {"tenant_id": tenant_id} if tenant_id else {}
    mems = list(get_db().memory_versions.find(q).sort("created_at", 1))
    for m in mems:
        m["effective_status"] = effective_status(m)
    return mems


def audit_trail(mem_id: str) -> dict:
    """Everything a reviewer needs to reconstruct why a memory is in its current state."""
    db = get_db()
    mem = db.memory_versions.find_one({"_id": mem_id})
    if not mem:
        raise MembraneError("memory not found")
    mem["effective_status"] = effective_status(mem)
    source = db.sources.find_one({"_id": mem.get("source_id")}) if mem.get("source_id") else None
    runs = list(db.simulation_runs.find(
        {"candidate_id": mem_id},
        {"results": 0}).sort("created_at", 1))
    return {"memory": mem, "source": source, "runs": runs}
