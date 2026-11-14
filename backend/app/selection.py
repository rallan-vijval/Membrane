from .common import Problem, digest

INDEX_NAME = "fixture_semantic_v1"


def index_definition(dimensions):
    return {"fields": [{"type": "vector", "path": "embedding", "numDimensions": dimensions, "similarity": "cosine"},
            *[{"type": "filter", "path": key} for key in ("workspace_id", "split", "enabled")]]}


def select(store, provider, candidate, embeddings=None):
    cfg = provider.config()
    query_text = candidate["text"] + " " + str(candidate["scope"])
    profile_id = None
    query_usage = {}
    if store.settings.governed_memory_enabled:
        from .memory_governance import batch_value, batch_usage
        if embeddings is None:
            raise Problem("embedding_unavailable", "Governed selection requires the independent embedding client", 503)
        profile_id = embeddings.describe()["profile_id"]
        batch = embeddings.embed_query(query_text)
        vectors = batch_value(batch, "vectors", [])
        if len(vectors) != 1 or batch_value(batch, "profile_id") != profile_id:
            raise Problem("dimension_mismatch", "Fixture query embedding profile differs", 503)
        vector = vectors[0]
        query_usage = batch_usage(batch)
    else:
        vector = provider.embed([query_text])[0]
    if len(vector) != cfg["embedding_dimensions"]:
        raise Problem("dimension_mismatch", "Fixture query embedding dimension differs", 503)
    try:
        neighbors = list(store.fixtures.aggregate([
            {"$vectorSearch": {"index": store.settings.fixture_index, "path": "embedding", "queryVector": vector,
                "numCandidates": 100, "limit": 4, "filter": store.query(split="development", enabled=True)}},
            {"$set": {"semantic_score": {"$meta": "vectorSearchScore"}}}, {"$project": {"_id": 0}}]))
    except Exception:
        raise Problem("search_unavailable", "Atlas Vector Search query failed; no substitute selection is permitted", 503)
    if len(neighbors) < 4:
        raise Problem("selection_incomplete", "Vector Search returned fewer than four development fixtures", 503)
    all_tasks = list(store.fixtures.find(store.query(split="development", enabled=True), {"_id": 0}).sort("fixture_id", 1))
    if len(all_tasks) < 24:
        raise Problem("selection_incomplete", "Seed at least 24 development fixtures", 503)
    selected = {}
    def add(task, reason, score=None):
        if task.get("split") != "development" or not task.get("enabled") or task.get("workspace_id") != store.workspace:
            raise Problem("selection_invalid", "Selection crossed workspace/split boundary")
        if task.get("embedding_model") != cfg["embedding_model"] or len(task.get("embedding", [])) != cfg["embedding_dimensions"]:
            raise Problem("dimension_mismatch", "Indexed fixture embeddings use a different model or dimension")
        if profile_id is not None and task.get("profile_id") != profile_id:
            raise Problem("dimension_mismatch", "Indexed fixture uses a different embedding profile")
        case_id = task["fixture_id"]
        if case_id not in selected:
            selected[case_id] = {"case_id": case_id, "description": task["description"], "task": task["task"],
                                 "reasons": [], "semantic_score": score}
        selected[case_id]["reasons"].append(reason)
        if score is not None:
            selected[case_id]["semantic_score"] = score
    sentinels = [t for t in all_tasks if t.get("sentinel")]
    if len(sentinels) != 5:
        raise Problem("selection_incomplete", "Exactly five policy sentinels are required")
    for task in sentinels:
        add(task, "mandatory_policy_sentinel")
    for task in neighbors:
        add(task, "atlas_vector_search", task.get("semantic_score"))
    # Neighbor IDs come from seeded Atlas fixtures, not model output.
    seed = next(t for t in all_tasks if t["fixture_id"] == "development-00")
    for neighbor_id in seed["neighbors"]:
        add(next(t for t in all_tasks if t["fixture_id"] == neighbor_id), "deterministic_scope_neighbor")
    for task in all_tasks:
        if len(selected) >= 12:
            break
        if task["fixture_id"] not in selected:
            add(task, "stable_fill")
    if len(selected) != 12:
        raise Problem("selection_incomplete", "Admission requires exactly twelve distinct cases")
    return list(selected.values()), {"index": store.settings.fixture_index, "query_text": query_text, "query_hash": digest(query_text),
        "embedding_model": cfg["embedding_model"], "dimensions": len(vector), "filter": store.query(split="development", enabled=True),
        "profile_id": profile_id, "embedding_usage": query_usage}
