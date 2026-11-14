"""Explicit, non-destructive setup. Model probes and embedding seed are billable."""
import argparse
import json
import time
from datetime import datetime, timedelta

from PIL import Image, ImageDraw
from pymongo.operations import SearchIndexModel

from backend.app.common import digest, now
from backend.app.config import ROOT, Settings
from backend.app.fixtures import exception, tasks
from backend.app.integration_bridge import Embeddings
from backend.app.memory_governance import MEMORY_COLLECTION, MEMORY_INDEX, batch_value, content_hash, index_definition as memory_definition
from backend.app.policy import POLICY
from backend.app.preflight import run_preflight
from backend.app.provider import Provider
from backend.app.selection import index_definition
from backend.app.store import Store


def seed(store, provider=None):
    store.indexes()
    cfg = store.settings
    exc = exception()
    store.db.trusted_exceptions.update_one(store.query(exception_id=exc["exception_id"]), {"$setOnInsert": store.doc(**exc)}, upsert=True)
    for task in tasks():
        store.fixtures.update_one(store.query(fixture_id=task["fixture_id"]), {"$setOnInsert": store.doc(**task)}, upsert=True)
    exceptions = list(store.db.trusted_exceptions.find(store.query(), {"_id": 0, "created_at": 0}))
    exceptions.sort(key=lambda e: e["exception_id"])
    policy_hash = digest({"policy": POLICY, "exceptions": exceptions})
    initial = "version_initial_v2" if cfg.governed_memory_enabled else "version_initial_v1"
    store.db.memory_versions.update_one(store.query(version_id=initial), {"$setOnInsert": store.doc(
        version_id=initial, parent_version_id=None, memories=[], candidate_id=None, run_id=None, policy_hash=policy_hash)}, upsert=True)
    store.db.workspace_state.update_one(store.query(), {"$setOnInsert": store.doc(active_memory_version_id=initial,
        revision=0, pending_receipt=None, voice_characters=0, governance_version=2 if cfg.governed_memory_enabled else 1)}, upsert=True)
    if cfg.governed_memory_enabled and store.get("workspace_state", "workspace_id", store.workspace).get("governance_version") != 2:
        raise ValueError("Use a separate initialized v2 workspace; no automatic migration")
    if not provider:
        return
    embeddings = Embeddings(cfg, getattr(provider, "_semaphore", None)) if cfg.governed_memory_enabled else None
    profile_id = embeddings.describe()["profile_id"] if embeddings else None
    docs = list(store.fixtures.find(store.query(), {"_id": 0}).sort("fixture_id", 1))
    if embeddings and any(d.get("embedding") and d.get("profile_id") != profile_id for d in docs):
        raise ValueError("Existing fixture vectors use another profile; preserve them and choose a separate profile/workspace")
    pending = [d for d in docs if d.get("embedding_model") != cfg.embedding_model or len(d.get("embedding", [])) != cfg.embedding_dimensions]
    for offset in range(0, len(pending), 16):
        batch = pending[offset:offset + 16]
        vectors = batch_value(embeddings.embed_documents([d["description"] for d in batch]), "vectors") if embeddings else provider.embed([d["description"] for d in batch])
        if len(vectors) != len(batch) or any(len(v) != cfg.embedding_dimensions for v in vectors):
            raise ValueError("Unexpected document vector count/dimensions")
        for doc, vector in zip(batch, vectors):
            store.fixtures.update_one(store.query(fixture_id=doc["fixture_id"]), {"$set": {
                "embedding": vector, "embedding_model": cfg.embedding_model,
                "embedding_version": "fixture-description-v1", "profile_id": profile_id}})
    if embeddings:
        collection = store.db[MEMORY_COLLECTION]
        probe = collection.find_one(store.query(memory_id="memory_probe_v2"))
        if probe and probe.get("profile_id") != profile_id:
            raise ValueError("Existing memory probe uses a different profile")
        if not probe:
            text, scope, at = "Synthetic known-neighbor memory retrieval probe; never activated", {"kind": "preference", "order_id": None, "customer_id": None, "exception_id": None}, now()
            vector = batch_value(embeddings.embed_documents([text]), "vectors")[0]
            if len(vector) != cfg.embedding_dimensions:
                raise ValueError("Memory probe dimensions differ")
            collection.update_one(store.query(memory_id="memory_probe_v2"), {"$setOnInsert": store.doc(
                memory_id="memory_probe_v2", text=text, scope=scope, ttl_seconds=3600, content_hash=content_hash(text, scope),
                candidate_id="probe_not_a_candidate", version_id="probe_not_an_active_version", activated_at=at,
                expires_at=(datetime.fromisoformat(at) + timedelta(days=365)).isoformat(), profile_id=profile_id, embedding=vector,
                synthetic_probe=True)}, upsert=True)


def setup_indexes(store):
    cfg = store.settings
    definitions = [(store.fixtures, cfg.fixture_index, index_definition(cfg.embedding_dimensions))]
    if cfg.governed_memory_enabled:
        definitions.append((store.db[MEMORY_COLLECTION], MEMORY_INDEX, memory_definition(cfg.embedding_dimensions)))
    for collection, name, definition in definitions:
        print(json.dumps({"collection": collection.name, "index": name, "definition": definition}, indent=2))
        existing = list(collection.list_search_indexes(name))
        if existing and existing[0].get("latestDefinition") != definition:
            raise ValueError("Existing index definition differs; do not overwrite")
        if not existing:
            collection.create_search_index(SearchIndexModel(name=name, definition=definition, type="vectorSearch"))
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            found = list(collection.list_search_indexes(name))
            if found and found[0].get("queryable"):
                break
            time.sleep(2)
        else:
            raise TimeoutError("Bounded Search readiness wait expired")
    print("Configured indexes queryable; run known-neighbor preflight before connected acceptance")


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
        screenshot(ROOT / "fixtures" / "support-4821.png")
    elif args.command == "seed":
        seed(store, provider if args.with_embeddings else None)
        print("Workspace-scoped seed complete; unrelated data preserved. Embeddings: " + str(args.with_embeddings))
    elif args.command == "index":
        setup_indexes(store)
    else:
        report = run_preflight(store, provider)
        print(json.dumps(report, indent=2))
        if any(c["status"] not in ("ready", "disabled") for c in report["checks"].values()):
            raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Setup failed. Check local keys, selected provider/model, workspace and Search permissions. Secret-bearing details are omitted.")
        raise SystemExit(1)
