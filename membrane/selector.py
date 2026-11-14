"""Choose which frozen tasks to replay for a candidate memory.

Atlas Vector Search finds the past cases most related to what the memory is about.
Fixed policy tests always run as well: similarity can miss the case that matters,
and the fixed set includes another tenant, so every run also checks for leaks.
"""
from __future__ import annotations

import logging

from .db import get_db

log = logging.getLogger("membrane.selector")

FIXTURE_INDEX = "fixture_vec"


def select_tests(candidate_id: str, k: int = 5) -> list[dict]:
    """Returns [{"task_id", "why": "vector" | "scope" | "fixed", "score"?}], deduplicated."""
    db = get_db()
    cand = db.memory_versions.find_one({"_id": candidate_id})
    if not cand:
        raise ValueError("candidate not found")

    picked: dict[str, dict] = {}
    try:
        hits = db.task_fixtures.aggregate([
            {"$vectorSearch": {
                "index": FIXTURE_INDEX, "path": "message", "query": {"text": cand["text"]},
                "numCandidates": 50, "limit": k,
                "filter": {"tenant_id": cand["tenant_id"]},
            }},
            {"$project": {"_id": 1, "score": {"$meta": "vectorSearchScore"}}},
        ])
        for h in hits:
            picked[h["_id"]] = {"task_id": h["_id"], "why": "vector", "score": round(h["score"], 4)}
    except Exception as exc:
        log.warning("vector test selection unavailable, running fixed tests only: %s", exc)

    scope = cand.get("scope") or {}
    if scope.get("kind") == "order":
        for t in db.task_fixtures.find(
                {"tenant_id": cand["tenant_id"], "order.id": scope["order_id"]}, {"_id": 1}):
            picked.setdefault(t["_id"], {"task_id": t["_id"], "why": "scope"})

    for t in db.task_fixtures.find({"fixed": True}, {"_id": 1}).sort("_id", 1):
        picked.setdefault(t["_id"], {"task_id": t["_id"], "why": "fixed"})
    return list(picked.values())
