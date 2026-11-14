"""Export schema-validated synthetic API examples; no provider/database calls."""
import json

from backend.app.config import ROOT
from backend.app.models import Candidate, ErrorResponse, Health, Run, Source, Version, MemoryEntries, TaskOptions, RevokeResult


def examples():
    timestamp = "2026-11-14T17:00:00+00:00"
    candidate = Candidate(candidate_id="candidate_SYNTHETIC", created_at=timestamp,
        source_id="source_SYNTHETIC", text="All VIP customers can keep refunded items.",
        scope={"kind": "global"}, parent_candidate_id=None, base_version_id="version_initial_v1",
        content_hash="SYNTHETIC_EXAMPLE_NOT_A_REAL_HASH", status="staged")
    run = Run(run_id="run_SYNTHETIC", candidate_id=candidate.candidate_id, created_at=timestamp,
        status="queued", admission=None, reasons=[], progress={"completed": 0, "total": 48},
        selection=[], selection_metadata={}, cases=[], summary={},
        config={"provider": "SYNTHETIC DOCUMENTATION EXAMPLE", "agent_model": "not-a-real-model"},
        usage={"model_calls": 0}, live=False, base_version_id=candidate.base_version_id,
        candidate_hash=candidate.content_hash)
    unavailable = {"status": "unavailable", "reason": "Configure local credentials and run preflight"}
    docs = {
        "health_unconfigured": Health(database=unavailable, model=unavailable, search=unavailable,
            voice={"status": "disabled", "reason": "Optional voice disabled"}, workspace_id="membrane-demo-v1"),
        "source": Source(source_id=candidate.source_id, created_at=timestamp, sha256="SYNTHETIC_EXAMPLE",
            mime_type="image/png", image_url=f"/api/sources/{candidate.source_id}/image",
            extracted_text="Order 4821 only: exception exc-4821 permits a refund without return.",
            quotation="Order 4821 only", proposed_text="Order-specific refund exception for order 4821.",
            proposed_scope={"kind": "order", "order_id": "4821", "customer_id": "customer-4821", "exception_id": "exc-4821"},
            provenance={"synthetic": True, "notice": "Documentation fixture; not an actual extraction"}),
        "active_version": Version(version_id="version_initial_v1", created_at=timestamp,
            parent_version_id=None, memories=[], policy_hash="SYNTHETIC_EXAMPLE"),
        "candidate_staged": candidate,
        "candidate_eligible": candidate.model_copy(update={"status": "eligible", "latest_run_id": run.run_id}),
        "candidate_quarantined": candidate.model_copy(update={"status": "quarantined", "latest_run_id": run.run_id}),
        "run_queued": run,
        "run_inconclusive": run.model_copy(update={"status": "inconclusive", "admission": "inconclusive",
            "reasons": ["Synthetic example: Vector Search unavailable; no substitute passing suite"]}),
        "error_stale_approval": ErrorResponse(error={"code": "stale_evidence",
            "message": "Approval requires exact current passing candidate, base, and policy evidence", "details": {}}),
        "memory_entries_empty": MemoryEntries(version_id="version_initial_v2", evaluated_at=timestamp, items=[], truncated=False),
        "task_options": TaskOptions(items=[{"fixture_id": "development-01", "description": "SYNTHETIC order 4821 task choice"}], truncated=False),
        "revoke_result": RevokeResult(version_id="version_SYNTHETIC_after_revoke", event_id="event_SYNTHETIC_revoke"),
    }
    # Revalidate copies as well: model_copy does not itself validate updates.
    return {name: type(doc).model_validate(doc.model_dump()).model_dump() for name, doc in docs.items()}


if __name__ == "__main__":
    path = ROOT / "contracts" / "examples.json"
    path.write_text(json.dumps({"notice": "SYNTHETIC DOCUMENTATION FIXTURES. Not recorded or live evidence.",
                                "examples": examples()}, indent=2) + "\n", encoding="utf-8")
    print(path)
