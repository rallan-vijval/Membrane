# Existing Atlas sandbox setup

## Governed-memory v2 additions

The new demo uses a separate workspace `membrane-demo-v2`, collection `task_fixtures_v2` with `fixture_semantic_v2`, and collection `memory_entries_v2` with `memory_semantic_v1`. Keep the legacy `task_fixtures`, its existing `fixture_vec`, and any `fixture_semantic_v1` untouched. The new profile selects direct Voyage embeddings at 1024 dimensions; it must not mix those vectors with OpenAI vectors.

`python -m scripts.backend_setup index` prints the exact selected collection/index definitions and applies each only if absent. For the Atlas UI fallback, fixture index fields are vector `embedding` (actual configured dimension, cosine), filters `workspace_id`, `split`, `enabled`. Memory index fields are vector `embedding` (same dimension, cosine), filters `workspace_id`, `memory_id`, `scope.kind`. Include every filter; membership filtering prevents an unactivated or revoked entry from being retrieved. Ordinary exact-scope queries also use the authoritative active membership and exact order/customer.

`seed --with-embeddings` inserts a synthetic, **unactivated** memory probe for `preflight` to exercise a real memory known-neighbor query independently of fixture retrieval. Active state still starts empty. Setup never authorizes an exception from the probe or changes unrelated records. A v1 workspace is not automatically migrated. Incompatible existing dimensions/profile/index definitions are a visible setup blocker; do not replace shared indexes or upgrade tiers.

Use the existing `Cluster0` and `membrane` database. Read-only plugin inspection on November 14, 2026 found MongoDB 9.0.7, dedicated M10, AWS US_WEST_1, IDLE. This is an observed snapshot, not a provisioning request or application connectivity test.

Existing collections include `sources`, `memory_versions`, `simulation_runs`, and `task_fixtures`. The legacy `fixture_vec` index uses Voyage auto-embeddings on `message` with a `tenant_id` filter. **Do not replace it.** The new API uses explicit OpenAI embeddings and workspace/split filters in a separate index named `fixture_semantic_v1`.

The application needs its own database user/connection string in local `.env`. Ask your Atlas project administrator for credentials scoped to the chosen database and the network access necessary for your machine. The plugin's successful connection does not establish local driver access. Do not broaden the access list or create administrative users automatically.

After verifying `EMBEDDING_MODEL` and the returned `EMBEDDING_DIMENSIONS`, seed the 36 synthetic fixtures with embeddings and create the new Search index using the commands in `backend-setup.md`. The normal collection indexes are workspace-scoped, with partial unique indexes excluding legacy records without `workspace_id`.

If programmatic Search index creation is unsupported/unauthorized:

1. Open Atlas, choose the existing cluster and its Search/Vector Search index creation interface.
2. Choose database `membrane`, collection `task_fixtures`, Vector Search JSON definition, and name `fixture_semantic_v1`.
3. Apply this JSON with the **actual configured integer dimension** in place of 1536:

```json
{
  "fields": [
    {"type": "vector", "path": "embedding", "numDimensions": 1536, "similarity": "cosine"},
    {"type": "filter", "path": "workspace_id"},
    {"type": "filter", "path": "split"},
    {"type": "filter", "path": "enabled"}
  ]
}
```

4. Wait until queryable, then run `python -m scripts.backend_setup preflight` from the activated environment. It must retrieve the known order-specific fixture in a real vector query. Missing or mismatched search is a visible degraded state and cannot silently select a passing suite.

Search references: [index definitions](https://www.mongodb.com/docs/vector-search/indexes/vector-search-type/) and [query syntax](https://www.mongodb.com/docs/manual/reference/operator/aggregation/vectorsearch/). If quota is insufficient, report the blocker; do not delete existing indexes or upgrade tiers.
