"""Non-destructive setup for the v1 review backend (separate from the legacy demo)."""
import argparse
import json
import time
from pathlib import Path

from PIL import Image, ImageDraw
from pymongo.operations import SearchIndexModel

from backend.app.common import digest, now
from backend.app.config import ROOT, Settings
from backend.app.fixtures import exception, tasks
from backend.app.policy import POLICY
from backend.app.provider import Provider
from backend.app.selection import INDEX_NAME, index_definition
from backend.app.store import Store


def seed(store, provider=None):
    store.indexes()
    exc = exception()
    store.db.trusted_exceptions.update_one(store.query(exception_id=exc["exception_id"]),
                                          {"$setOnInsert": store.doc(**exc)}, upsert=True)
    for task in tasks():
        store.db.task_fixtures.update_one(store.query(fixture_id=task["fixture_id"]),
                                         {"$setOnInsert": store.doc(**task)}, upsert=True)
    exceptions = list(store.db.trusted_exceptions.find(store.query(), {"_id": 0, "created_at": 0}))
    exceptions.sort(key=lambda e: e["exception_id"])
    policy_hash = digest({"policy": POLICY, "exceptions": exceptions})
    store.db.memory_versions.update_one(store.query(version_id="version_initial_v1"), {"$setOnInsert": store.doc(
        version_id="version_initial_v1", parent_version_id=None, memories=[], candidate_id=None, run_id=None, policy_hash=policy_hash)}, upsert=True)
    store.db.workspace_state.update_one(store.query(), {"$setOnInsert": store.doc(
        active_memory_version_id="version_initial_v1", revision=0, pending_receipt=None, voice_characters=0)}, upsert=True)
    if provider:
        docs = list(store.db.task_fixtures.find(store.query(), {"_id": 0}).sort("fixture_id", 1))
        pending = [d for d in docs if d.get("embedding_model") != provider.settings.embedding_model or len(d.get("embedding", [])) != provider.settings.embedding_dimensions]
        for offset in range(0, len(pending), 16):
            batch = pending[offset:offset + 16]
            vectors = provider.embed([d["description"] for d in batch])
            for doc, vector in zip(batch, vectors):
                store.db.task_fixtures.update_one(store.query(fixture_id=doc["fixture_id"]), {"$set": {
                    "embedding": vector, "embedding_model": provider.settings.embedding_model, "embedding_version": "fixture-description-v1"}})


def screenshot(path):
    image = Image.new("RGB", (1100, 520), "#f4f6f8")
    draw = ImageDraw.Draw(image)
    draw.text((40, 35), "SYNTHETIC SUPPORT SCREENSHOT - NOT REAL CUSTOMER DATA", fill="#101828", font_size=25)
    lines = ["Order: 4821", "Customer: customer-4821 (VIP)", "Supervisor note:",
             "A trusted order-specific exception permits a 5000-cent refund",
             "to the original payment method without a return for this order only.",
             "Exception reference: exc-4821", "Ownership must still be verified. Other orders are not covered."]
    for index, text in enumerate(lines):
        draw.text((40, 110 + index * 45), text, fill="#26364a", font_size=22)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["seed", "index", "preflight", "screenshot"])
    parser.add_argument("--with-embeddings", action="store_true", help="Makes billable embedding requests")
    args = parser.parse_args()
    cfg = Settings()
    store, provider = Store(cfg), Provider(cfg)
    if args.command == "screenshot":
        path = ROOT / "fixtures" / "support-4821.png"
        screenshot(path)
        print(str(path))
        return
    if args.command == "seed":
        seed(store, provider if args.with_embeddings else None)
        print("Workspace-scoped seed complete; unrelated data preserved. Embeddings: " + str(args.with_embeddings))
    elif args.command == "index":
        definition = index_definition(cfg.embedding_dimensions)
        print(json.dumps(definition, indent=2))
        indexes = list(store.db.task_fixtures.list_search_indexes(INDEX_NAME))
        if indexes:
            if indexes[0].get("latestDefinition") != definition:
                raise RuntimeError("Existing index definition differs; review manually, do not overwrite")
        else:
            store.db.task_fixtures.create_search_index(SearchIndexModel(name=INDEX_NAME, definition=definition, type="vectorSearch"))
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            found = list(store.db.task_fixtures.list_search_indexes(INDEX_NAME))
            if found and found[0].get("queryable"):
                print("Index queryable. Run preflight for known-neighbor verification.")
                return
            time.sleep(2)
        raise RuntimeError("Search index is not queryable yet; bounded wait expired")
    else:
        statuses = {}
        try:
            store.db.command("ping")
            version = store.db.command("buildInfo")["version"]
            statuses["database"] = {"status": "ready", "server_version": version}
        except Exception:
            statuses["database"] = {"status": "unavailable", "reason": "Check MONGODB_URI, database permissions, and Atlas network access"}
        model = {"status": "unavailable", "reason": "Check OPENAI_API_KEY and model IDs"}
        try:
            for model_id in {cfg.agent_model, cfg.vision_model, cfg.embedding_model}:
                if not model_id:
                    raise ValueError("Missing model ID")
                provider.client.models.retrieve(model_id)
            from io import BytesIO
            probe = Image.new("RGB", (200, 80), "white")
            ImageDraw.Draw(probe).text((10, 20), "SYNTHETIC TEST 4821", fill="black", font_size=16)
            data = BytesIO()
            probe.save(data, format="PNG")
            provider.extract(data.getvalue(), "image/png")
            task = tasks()[0]["task"]
            from backend.app.models import Attempt
            decision, raw, _ = provider.decide(task, [], lambda: None)
            Attempt.model_validate(decision)
            provider.embed(["synthetic known-neighbor check"])
            model = {"status": "ready", "reason": "Model access, vision/structured decisions, and embedding dimensions verified"}
        except Exception:
            pass
        statuses["model"] = model
        known = False
        try:
            fixture = store.db.task_fixtures.find_one(store.query(fixture_id="development-01"))
            if not fixture or fixture.get("embedding_model") != cfg.embedding_model:
                raise ValueError("Seed embeddings first")
            found = list(store.db.task_fixtures.aggregate([{"$vectorSearch": {"index": INDEX_NAME,
                "path": "embedding", "queryVector": fixture["embedding"], "exact": True, "limit": 4,
                "filter": store.query(split="development", enabled=True)}}, {"$project": {"fixture_id": 1}}]))
            known = "development-01" in [f["fixture_id"] for f in found]
            statuses["search"] = {"status": "ready" if known else "degraded", "reason": "Known-neighbor query " + ("passed" if known else "failed")}
        except Exception:
            statuses["search"] = {"status": "unavailable", "reason": "Seed embeddings and create fixture_semantic_v1; no fallback"}
        if statuses["database"]["status"] == "ready":
            store.db.workspace_state.update_one(store.query(), {"$set": {"preflight": {
                "checked_at": now(), "provider_config": provider.config(), "model": model, "known_neighbor_passed": known}}})
        print(json.dumps({"checks": statuses, "calls": {"admission_initial": 48, "admission_max_turns_before_retries": 144,
            "configured_cap": cfg.max_run_model_calls}, "preflight_is_billable": True}, indent=2))
        if any(item["status"] != "ready" for item in statuses.values()):
            raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Setup failed. Verify local credentials, configured model access, database permissions, and Search setup. Secret-bearing provider details are intentionally omitted.")
        raise SystemExit(1)
