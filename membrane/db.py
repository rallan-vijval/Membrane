"""MongoDB Atlas connection. Imported lazily so pure logic can be tested without a database."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from functools import lru_cache

DB_NAME_DEFAULT = "membrane"


def now() -> datetime:
    return datetime.now(timezone.utc)


@lru_cache(maxsize=1)
def get_db():
    from dotenv import load_dotenv
    from pymongo import MongoClient

    load_dotenv()
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI is not set. Copy .env.example to .env and fill it in.")
    client = MongoClient(uri, tz_aware=True, serverSelectionTimeoutMS=8000)
    return client[os.environ.get("DB_NAME", DB_NAME_DEFAULT)]


if __name__ == "__main__":
    db = get_db()
    print(db.client.admin.command("ping"))
    print("collections:", db.list_collection_names())
