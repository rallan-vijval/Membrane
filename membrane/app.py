"""Membrane API. Run with:  uvicorn membrane.app:app --reload"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import agent, fixtures, memory, runner, selector
from .compare import compare
from .db import get_db

app = FastAPI(title="Membrane", description="Preview what a new memory will make your agent do.")
STATIC = Path(__file__).parent / "static"


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except memory.MembraneError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except agent.AgentError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ------------------------------------------------------------------ request bodies

class SourceIn(BaseModel):
    tenant_id: str
    raw_text: str
    submitted_by: str = "reviewer"


class ProposeIn(BaseModel):
    raw_text: str


class CandidateIn(BaseModel):
    tenant_id: str
    text: str
    scope: dict = {"kind": "global"}
    source_id: str | None = None
    proposed_by: str = "agent:support-bot"


class TestIn(BaseModel):
    trials: int = 3


class AcceptIn(BaseModel):
    run_id: str
    reviewer: str = "reviewer"
    ttl_seconds: int | None = None


class QuarantineIn(BaseModel):
    reviewer: str = "reviewer"
    reason: str = "failed behavior preview"
    run_id: str | None = None


class ReviseIn(BaseModel):
    text: str
    scope: dict
    reviewer: str = "reviewer"


class RevokeIn(BaseModel):
    reviewer: str = "reviewer"
    reason: str = "revoked by reviewer"


class LiveIn(BaseModel):
    task_id: str


# ------------------------------------------------------------------ read

@app.get("/api/state")
def state(tenant_id: str | None = None):
    db = get_db()
    tasks = list(db.task_fixtures.find(
        {}, {"message": 1, "tenant_id": 1, "order.id": 1, "customer.tier": 1, "fixed": 1}).sort("_id", 1))
    return {
        "tenants": fixtures.TENANTS,
        "memories": memory.list_memories(tenant_id),
        "tasks": tasks,
        "model": {"provider": agent.provider(), "name": agent.model()},
        "demo": {"source": fixtures.DEMO_SOURCE_TEXT, "broad": fixtures.DEMO_BROAD_MEMORY,
                 "narrow": fixtures.DEMO_NARROW_MEMORY, "order_id": "4821"},
    }


@app.get("/api/memories/{mem_id}/audit")
def audit(mem_id: str):
    return _guard(memory.audit_trail, mem_id)


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    run = get_db().simulation_runs.find_one({"_id": run_id})
    if not run:
        raise HTTPException(404, "run not found")
    return run


# ------------------------------------------------------------------ stage + test

@app.post("/api/sources")
def add_source(body: SourceIn):
    return {"source_id": memory.save_source(body.raw_text, body.tenant_id, body.submitted_by)}


@app.post("/api/propose")
def propose(body: ProposeIn):
    """Let the agent write a memory from a source. The result is only a suggestion."""
    return _guard(agent.propose_memory, body.raw_text)


@app.post("/api/candidates")
def add_candidate(body: CandidateIn):
    mem_id = _guard(memory.stage_memory, body.text, body.source_id, body.tenant_id, body.scope,
                    proposed_by=body.proposed_by)
    return get_db().memory_versions.find_one({"_id": mem_id})


@app.post("/api/candidates/{mem_id}/test")
def test_candidate(mem_id: str, body: TestIn):
    cand = get_db().memory_versions.find_one({"_id": mem_id})
    if not cand:
        raise HTTPException(404, "candidate not found")
    if cand["status"] != "proposed":
        raise HTTPException(409, f"only a proposed memory can be tested (this one is {cand['status']})")
    selection = _guard(selector.select_tests, mem_id)
    run_id = _guard(runner.run_ab, mem_id, selection, max(1, min(body.trials, 5)))
    result = compare(run_id)
    return {"run_id": run_id, "selection": selection, "trials": body.trials, **result}


# ------------------------------------------------------------------ decisions

@app.post("/api/candidates/{mem_id}/accept")
def accept(mem_id: str, body: AcceptIn):
    return _guard(memory.accept, mem_id, body.run_id, body.reviewer, body.ttl_seconds)


@app.post("/api/candidates/{mem_id}/quarantine")
def quarantine(mem_id: str, body: QuarantineIn):
    return _guard(memory.quarantine, mem_id, body.reviewer, body.reason, body.run_id)


@app.post("/api/candidates/{mem_id}/revise")
def revise(mem_id: str, body: ReviseIn):
    new_id = _guard(memory.revise, mem_id, body.text, body.scope, body.reviewer)
    return get_db().memory_versions.find_one({"_id": new_id})


@app.post("/api/memories/{mem_id}/revoke")
def revoke(mem_id: str, body: RevokeIn):
    return _guard(memory.revoke, mem_id, body.reviewer, body.reason)


# ------------------------------------------------------------------ live agent

@app.post("/api/live")
def live(body: LiveIn):
    """Run the live agent (active memory only) on one frozen task. Tools are still simulated."""
    return _guard(runner.run_live, body.task_id)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
