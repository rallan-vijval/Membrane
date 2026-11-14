"""Bounded post-activation task execution. Never produces admission evidence."""
import time

from .common import Problem, digest, now, uid
from .models import Attempt, ActiveExecution
from .policy import check_attempt


def execute(service, fixture_id, body):
    s = service.store
    service.memory.require_enabled()
    service.reconcile()
    version = s.active()
    if body.base_version_id != version["version_id"]:
        raise Problem("stale_base", "Refresh active memory before executing the task")
    fixture = s.get(s.settings.fixture_collection, "fixture_id", fixture_id)
    if fixture.get("split") != "development" or not fixture.get("enabled"):
        raise Problem("task_unavailable", "Only enabled development tasks may be executed", 404)
    started = now()
    retrieval = service.memory.retrieve(fixture["task"], fixture_id, version, started)
    if s.active()["version_id"] != version["version_id"]:
        raise Problem("stale_base", "Active memory changed during task preparation")
    policy = service.policy_snapshot()
    result = {"side": "baseline", "repetition": 1, "raw_responses": [], "attempt": None,
        "tool_outcome": None, "checks": [], "error": None, "calls": 0, "input_tokens": 0, "output_tokens": 0,
        "latency_ms": 0, "input_hash": digest({"task": fixture["task"], "retrieval": retrieval, "config": service.provider.config(), "policy": policy})}
    def reserve():
        if result["calls"] >= 2:
            raise Problem("budget_exhausted", "Active task has a maximum of two attempted generation requests")
        result["calls"] += 1
    start = time.monotonic()
    trace_url = None
    try:
        with service.tracing.span("active_task", {"workspace_id": s.workspace, "fixture_id": fixture_id, "version_id": version["version_id"]}) as trace:
            data, raw, _ = service.provider.decide(fixture["task"], retrieval["entries"], reserve)
            result["raw_responses"] = [raw]
            trace_url = trace.trace_url
        usage = raw.get("usage") or {}
        result["input_tokens"], result["output_tokens"] = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
        result["attempt"] = Attempt.model_validate(data).model_dump()
        # Context frozen for the request is evidence, not authority for a later tool attempt.
        if s.active()["version_id"] != version["version_id"] or digest(service.policy_snapshot()) != digest(policy):
            raise Problem("active_authority_changed", "Memory or policy changed before simulated tool enforcement")
        service.memory.validate_frozen([retrieval], now())
        checks, outcome = check_attempt(result["attempt"], fixture["task"], policy["exceptions"], now())
        result["checks"], result["tool_outcome"] = checks, outcome
    except Exception as exc:
        result["error"] = exc.code if isinstance(exc, Problem) else "invalid_or_failed_response"
        if result["attempt"] and result["attempt"]["action"] == "refund_order":
            result["tool_outcome"] = {"allowed": False, "simulated": True, "reasons": ["Execution evidence failed fresh authority validation"]}
    result["latency_ms"] = int((time.monotonic() - start) * 1000)
    execution_id = uid("execution")
    document = s.doc(execution_id=execution_id, version_id=version["version_id"], fixture_id=fixture_id,
        retrieval=retrieval, execution=result, config=service.provider.config(),
        usage={"generation_calls": result["calls"], "input_tokens": result["input_tokens"], "output_tokens": result["output_tokens"],
               "retrieval": retrieval["usage"], "latency_ms": result["latency_ms"]}, trace_url=trace_url,
        frozen_task=fixture["task"], policy_hash=digest(policy), admission_evidence=False)
    s.db.live_executions.insert_one(document)
    return service.public(ActiveExecution, document)
