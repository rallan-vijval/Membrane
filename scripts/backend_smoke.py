"""Explicit billable live API smoke flow. Run only after setup and the server are running."""
import argparse
import json
import time
from uuid import uuid4

import httpx

from backend.app.config import ROOT
from backend.app.fixtures import BROAD, NARROW


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approve", action="store_true", help="Explicitly approve the exact eligible scoped revision; changes active memory")
    args = parser.parse_args()
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=120) as client:
        def call(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()
        def run(candidate_id):
            run_id = call("POST", f"/api/candidates/{candidate_id}/runs")["run_id"]
            deadline = time.monotonic() + 900
            while time.monotonic() < deadline:
                doc = call("GET", f"/api/runs/{run_id}")
                if doc["status"] not in ("queued", "running"):
                    return doc
                time.sleep(2)
            raise RuntimeError("Run did not finish within the bounded smoke timeout")
        health = call("GET", "/api/health")
        if any(health[key]["status"] != "ready" for key in ("database", "model", "search")):
            print(json.dumps(health, indent=2))
            raise SystemExit("Configure and pass preflight before live smoke")
        base = call("GET", "/api/memory/active")
        with (ROOT / "fixtures" / "support-4821.png").open("rb") as image:
            source = call("POST", "/api/sources", files={"file": ("support-4821.png", image, "image/png")})
        candidate = call("POST", "/api/candidates", json={"source_id": source["source_id"], "text": BROAD,
            "scope": {"kind": "global"}, "base_version_id": base["version_id"]})
        broad = run(candidate["candidate_id"])
        # Report the actual observation. A resistant model must never be presented as a fabricated failure.
        print(json.dumps({"broad_run_id": broad["run_id"], "observed_admission": broad["admission"], "reasons": broad["reasons"]}, indent=2))
        if broad["admission"] != "quarantine":
            call("POST", f"/api/candidates/{candidate['candidate_id']}/quarantine",
                 headers={"Idempotency-Key": uuid4().hex}, json={"reason": "Manual demo quarantine of broad rule; observed result retained"})
        revised = call("POST", f"/api/candidates/{candidate['candidate_id']}/revise", json={"text": NARROW,
            "scope": {"kind": "order", "order_id": "4821", "customer_id": "customer-4821", "exception_id": "exc-4821"}})
        narrow = run(revised["candidate_id"])
        print(json.dumps({"narrow_run_id": narrow["run_id"], "observed_admission": narrow["admission"], "reasons": narrow["reasons"]}, indent=2))
        if narrow["admission"] != "eligible":
            raise SystemExit("Scoped revision did not pass; no activation")
        if args.approve:
            call("POST", f"/api/candidates/{revised['candidate_id']}/approve", headers={"Idempotency-Key": uuid4().hex},
                 json={"run_id": narrow["run_id"], "reason": "Explicit live smoke reviewer approval"})
            active = call("GET", "/api/memory/active")
            assert active["candidate_id"] == revised["candidate_id"]
            assert call("GET", "/api/history")["versions"][0]["version_id"] == active["version_id"]
            print("Exact eligible version activated and reloaded from Atlas. Restart the service and verify active/history again.")
        else:
            print("Eligible revision retained for explicit reviewer approval; active memory was not changed.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("Live smoke failed; inspect the API's redacted status and persisted run evidence. No success is claimed.")
