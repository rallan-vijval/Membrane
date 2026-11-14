"""Atlas is the only application store. Test doubles are injected explicitly in tests."""
from pymongo import ASCENDING, MongoClient, ReturnDocument

from .common import Problem, now

COLLECTIONS = ("workspace_state", "sources", "trusted_exceptions", "memory_candidates", "memory_versions",
               "task_fixtures", "evaluation_runs", "case_results", "review_events", "audio_assets")


class Store:
    def __init__(self, settings, db=None):
        self.settings = settings
        self.workspace = settings.workspace_id
        self.client = None
        self._db = db

    @property
    def db(self):
        if self._db is None:
            uri = self.settings.mongodb_uri.get_secret_value()
            if not uri or "<" in uri:
                raise Problem("database_unavailable", "Set MONGODB_URI in the local .env file", 503)
            self.client = MongoClient(uri, serverSelectionTimeoutMS=4000, connectTimeoutMS=4000, tz_aware=True)
            self._db = self.client[self.settings.mongodb_db]
        return self._db

    def query(self, **where):
        return {"workspace_id": self.workspace, **where}

    def doc(self, **fields):
        return {"workspace_id": self.workspace, "schema_version": 1, "created_at": now(), **fields}

    def get(self, collection, key, value):
        doc = self.db[collection].find_one(self.query(**{key: value}), {"_id": 0})
        if not doc:
            raise Problem("not_found", f"{collection} record not found", 404)
        return doc

    def indexes(self):
        for collection, fields in [("workspace_state", []), ("sources", ["source_id"]),
                                   ("trusted_exceptions", ["exception_id"]), ("memory_candidates", ["candidate_id"]),
                                   ("memory_versions", ["version_id"]), ("task_fixtures", ["fixture_id"]),
                                   ("evaluation_runs", ["run_id"]), ("case_results", ["run_id", "case_id", "side", "repetition"]),
                                   ("review_events", ["idempotency_key"]), ("audio_assets", ["audio_id"])]:
            # Existing unrelated documents without workspace_id are excluded.
            self.db[collection].create_index([(f, ASCENDING) for f in ["workspace_id", *fields]], unique=True,
                partialFilterExpression={"workspace_id": {"$type": "string"}}, name="membrane_v1_unique_" + "_".join(fields or ["workspace"]))
        for collection in ("memory_candidates", "evaluation_runs", "review_events"):
            self.db[collection].create_index([("workspace_id", 1), ("created_at", -1)])
        self.db.evaluation_runs.create_index([("workspace_id", 1), ("status", 1), ("lease_until", 1)])

    def active(self):
        state = self.get("workspace_state", "workspace_id", self.workspace)
        return self.get("memory_versions", "version_id", state["active_memory_version_id"])

    def list(self, collection):
        items = list(self.db[collection].find(self.query(), {"_id": 0}).sort("created_at", -1).limit(101))
        return items[:100], len(items) > 100

    def reserve_call(self, run_id):
        run = self.db.evaluation_runs.find_one_and_update(
            self.query(run_id=run_id, model_calls={"$lt": self.settings.max_run_model_calls}),
            {"$inc": {"model_calls": 1}}, return_document=ReturnDocument.AFTER)
        if not run:
            raise Problem("budget_exhausted", "Model call cap exhausted; run is inconclusive")
