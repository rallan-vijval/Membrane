"""Explicit billable capability checks. Ordinary health reads never call model APIs."""
from io import BytesIO

from PIL import Image, ImageDraw

from .common import now
from .fixtures import tasks
from .integration_bridge import Embeddings
from .memory_governance import MEMORY_COLLECTION, MEMORY_INDEX, batch_value, index_definition as memory_definition
from .models import Attempt
from .selection import index_definition as fixture_definition


def run_preflight(store, provider):
    cfg = store.settings
    statuses = {}
    profile_id = None
    usage = {}
    database_ready = False
    try:
        store.db.command("ping")
        version = store.db.command("buildInfo")["version"]
        state = store.get("workspace_state", "workspace_id", store.workspace)
        if cfg.governed_memory_enabled and state.get("governance_version") != 2:
            raise ValueError("Seed the separate v2 workspace")
        database_ready = True
        statuses["database"] = {"status": "ready", "reason": f"Atlas ping and workspace access succeeded; server {version}"}
    except Exception:
        statuses["database"] = {"status": "unavailable", "reason": "Set MONGODB_URI, verify access, and seed the selected workspace"}
    try:
        provider.client.models.retrieve(cfg.agent_model)
        data, raw, calls = provider.decide(tasks()[0]["task"], [], lambda: None)
        Attempt.model_validate(data)
        usage["generation"] = {"attempted_calls": calls, "usage": raw.get("usage")}
        statuses["model"] = {"status": "ready", "reason": "Configured generation model returned a locally validated structured decision"}
    except Exception:
        statuses["model"] = {"status": "unavailable", "reason": "Check DEEPSEEK_API_KEY (or explicit OPENAI_API_KEY), AGENT_MODEL and provider access"}
    try:
        image = Image.new("RGB", (240, 80), "white")
        ImageDraw.Draw(image).text((10, 20), "SYNTHETIC ORDER 4821", fill="black", font_size=16)
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        _, provenance = provider.extract(buffer.getvalue(), "image/png")
        usage["vision"] = provenance.get("usage")
        statuses["vision"] = {"status": "ready", "reason": "Actual image extraction and local source schema checks passed"}
    except Exception:
        statuses["vision"] = {"status": "unavailable", "reason": "Check VISION_PROVIDER/key/VISION_MODEL and actual image input support"}
    try:
        if cfg.governed_memory_enabled:
            embeddings = Embeddings(cfg, getattr(provider, "_semaphore", None))
            profile_id = embeddings.describe()["profile_id"]
            batch = embeddings.embed_query("synthetic support known-neighbor capability probe")
            vectors = batch_value(batch, "vectors")
            if len(vectors) != 1 or len(vectors[0]) != cfg.embedding_dimensions or batch_value(batch, "profile_id") != profile_id:
                raise ValueError("Embedding profile/dimensions mismatch")
            from .memory_governance import batch_usage
            usage["embeddings"] = batch_usage(batch)
        else:
            provider.embed(["synthetic support capability probe"])
        statuses["embeddings"] = {"status": "ready", "reason": "Selected embedding provider/model/dimensions verified independently of generation"}
    except Exception:
        statuses["embeddings"] = {"status": "unavailable", "reason": "Integrate Agent C facade; verify VOYAGE_API_KEY or OPENAI_API_KEY and embedding profile"}
    known = False
    try:
        indexes = list(store.fixtures.list_search_indexes(cfg.fixture_index))
        if not indexes or not indexes[0].get("queryable") or indexes[0].get("latestDefinition") != fixture_definition(cfg.embedding_dimensions):
            raise ValueError("Fixture Search not ready")
        fixture = store.fixtures.find_one(store.query(fixture_id="development-01"))
        if not fixture or fixture.get("embedding_model") != cfg.embedding_model or (cfg.governed_memory_enabled and fixture.get("profile_id") != profile_id):
            raise ValueError("Seed current embedding profile")
        neighbors = list(store.fixtures.aggregate([{"$vectorSearch": {"index": cfg.fixture_index, "path": "embedding",
            "queryVector": fixture["embedding"], "exact": True, "limit": 4,
            "filter": store.query(split="development", enabled=True)}}, {"$project": {"fixture_id": 1}}]))
        known = "development-01" in [d["fixture_id"] for d in neighbors]
        statuses["search"] = {"status": "ready" if known else "degraded", "reason": "Fixture known-neighbor query " + ("passed" if known else "failed")}
    except Exception:
        statuses["search"] = {"status": "unavailable", "reason": "Seed embeddings and create the configured fixture index; no fallback"}
    memory_known = False
    if cfg.governed_memory_enabled:
        try:
            indexes = list(store.db[MEMORY_COLLECTION].list_search_indexes(MEMORY_INDEX))
            if not indexes or not indexes[0].get("queryable") or indexes[0].get("latestDefinition") != memory_definition(cfg.embedding_dimensions):
                raise ValueError("Memory Search not ready")
            probe = store.get(MEMORY_COLLECTION, "memory_id", "memory_probe_v2")
            if probe["profile_id"] != profile_id:
                raise ValueError("Memory probe has a different profile")
            neighbors = list(store.db[MEMORY_COLLECTION].aggregate([{"$vectorSearch": {"index": MEMORY_INDEX,
                "path": "embedding", "queryVector": probe["embedding"], "exact": True, "limit": 1,
                "filter": store.query(memory_id={"$in": ["memory_probe_v2"]})}}, {"$project": {"memory_id": 1}}]))
            memory_known = any(d["memory_id"] == "memory_probe_v2" for d in neighbors)
            statuses["memory_search"] = {"status": "ready" if memory_known else "degraded", "reason": "Memory known-neighbor query " + ("passed" if memory_known else "failed")}
        except Exception:
            statuses["memory_search"] = {"status": "unavailable", "reason": "Seed the unactivated synthetic memory probe and create memory_semantic_v1"}
    else:
        statuses["memory_search"] = {"status": "disabled", "reason": "Governed memory is disabled"}
    if database_ready:
        store.db.workspace_state.update_one(store.query(), {"$set": {"preflight": {
            "checked_at": now(), "provider_config": provider.config(), "profile_id": profile_id,
            "model": statuses["model"], "vision": statuses["vision"], "embeddings": statuses["embeddings"],
            "known_neighbor_passed": known, "memory_known_neighbor_passed": memory_known}}})
    return {"checks": statuses, "usage": usage, "calls": {"admission_initial": 48,
        "single_turn_max_with_one_transient_retry": 96, "configured_cap": cfg.max_run_model_calls}, "preflight_is_billable": True}
