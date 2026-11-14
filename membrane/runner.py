"""Run the same frozen tasks in two isolated views.

View A: current memory.            View B: current memory + the candidate.
Each trial is a fresh agent session. Nothing is shared between runs, and the candidate is
handed to View B directly: it is never written into active memory.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from . import agent
from .db import get_db, now
from .memory import get_memories, new_id

MAX_WORKERS = 6


def _one(job: dict) -> dict:
    base = {k: job[k] for k in ("task_id", "view", "trial", "memory_ids", "retrieval")}
    try:
        out = agent.run_task(job["task"], job["memories"])
        return {**base, **out}
    except Exception as exc:  # recorded, and makes the run inconclusive
        return {**base, "tool_calls": [], "final_text": "", "error": str(exc)[:300]}


def run_ab(candidate_id: str, selection: list[dict], trials: int = 3) -> str:
    """selection: output of selector.select_tests. Returns the simulation run id."""
    db = get_db()
    cand = db.memory_versions.find_one({"_id": candidate_id})
    if not cand:
        raise ValueError("candidate not found")
    task_ids = [s["task_id"] for s in selection]
    tasks = {t["_id"]: t for t in db.task_fixtures.find({"_id": {"$in": task_ids}})}

    jobs = []
    for tid in task_ids:
        task = tasks[tid]
        for view in ("A", "B"):
            mems, mode = get_memories(task["tenant_id"], task["message"], task["order"]["id"],
                                      view, candidate_id)
            for trial in range(trials):
                jobs.append({"task_id": tid, "view": view, "trial": trial, "task": task,
                             "memories": mems, "memory_ids": [m["_id"] for m in mems],
                             "retrieval": mode})

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        results = list(pool.map(_one, jobs))

    run_id = new_id("run")
    db.simulation_runs.insert_one({
        "_id": run_id,
        "candidate_id": candidate_id,
        "candidate_text": cand["text"],
        "candidate_scope": cand["scope"],
        "tenant_id": cand["tenant_id"],
        "task_ids": task_ids,
        "selection": selection,
        "trials": trials,
        "model": {"provider": agent.provider(), "name": agent.model()},
        "results": results,
        "created_at": now(),
    })
    return run_id


def run_live(task_id: str) -> dict:
    """What the live agent does right now for one task (active memory only)."""
    db = get_db()
    task = db.task_fixtures.find_one({"_id": task_id})
    if not task:
        raise ValueError("task not found")
    mems, mode = get_memories(task["tenant_id"], task["message"], task["order"]["id"], "A")
    out = agent.run_task(task, mems)
    return {
        "task_id": task_id, "tenant_id": task["tenant_id"], "order_id": task["order"]["id"],
        "message": task["message"],
        "memories_used": [{"_id": m["_id"], "text": m["text"], "scope": m["scope"]} for m in mems],
        "retrieval": mode, **out,
    }
