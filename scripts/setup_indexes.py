"""Create the two Atlas Vector Search indexes (auto-embedding with Voyage, done by Atlas).

Usage:  python -m scripts.setup_indexes
Safe to re-run: existing indexes are left alone.
"""
from pymongo.operations import SearchIndexModel

from membrane.db import get_db

INDEXES = {
    "task_fixtures": ("fixture_vec", {"fields": [
        {"type": "autoEmbed", "path": "message", "model": "voyage-4", "modality": "text"},
        {"type": "filter", "path": "tenant_id"},
    ]}),
    "memory_versions": ("memory_vec", {"fields": [
        {"type": "autoEmbed", "path": "text", "model": "voyage-4", "modality": "text"},
        {"type": "filter", "path": "tenant_id"},
        {"type": "filter", "path": "status"},
        {"type": "filter", "path": "expires_at"},
        {"type": "filter", "path": "scope.kind"},
        {"type": "filter", "path": "scope.order_id"},
    ]}),
}


def main():
    db = get_db()
    existing = set(db.list_collection_names())
    for coll, (name, definition) in INDEXES.items():
        if coll not in existing:
            db.create_collection(coll)
        have = {i["name"]: i for i in db[coll].list_search_indexes()}
        if name in have:
            print(f"{coll}.{name}: exists (status {have[name].get('status')})")
            continue
        db[coll].create_search_index(SearchIndexModel(definition=definition, name=name, type="vectorSearch"))
        print(f"{coll}.{name}: created, building…")


if __name__ == "__main__":
    main()
