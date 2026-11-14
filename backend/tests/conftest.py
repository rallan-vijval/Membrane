import mongomock
import pytest

from backend.app.config import Settings
from backend.app.store import Store
from backend.app.service import Service
from backend.app.fixtures import tasks
from scripts.backend_setup import seed


class FakeProvider:
    """Explicit deterministic test provider. Never installed by the application."""
    def __init__(self, settings):
        self.settings = settings
        self.calls = []
        self.fail = False
        self.unsafe_broad = True

    def config(self):
        return {"provider": "TEST ONLY", "agent_model": "synthetic-unit-test", "embedding_model": "test-embedding",
                "embedding_dimensions": 3, "max_calls": self.settings.max_run_model_calls}

    def embed(self, texts):
        return [[1.0, 0.0, 0.0] for _ in texts]

    def extract(self, data, mime):
        return {"extracted_text": "Order 4821 exception", "quotation": "Order 4821", "proposed_text": "order rule",
                "proposed_scope": {"kind": "order", "order_id": "4821", "customer_id": "customer-4821", "exception_id": "exc-4821"}}, {"synthetic": True}

    def decide(self, task, memories, reserve, deadline=None):
        reserve()
        self.calls.append((task.copy(), list(memories)))
        if self.fail:
            raise RuntimeError("Explicit test failure")
        scope = memories[-1].get("scope", {}) if memories else {}
        narrow = scope.get("order_id") == task["order_id"] and task["order_id"] == "4821"
        broad = self.unsafe_broad and any("All VIP" in m["text"] for m in memories) and task["tier"] == "VIP"
        if task["kind"] == "shipping" or task["requested_destination"] != task["original_destination"]:
            action = "answer"
        elif not task["verified"]:
            action = "request_verification"
        elif task["return_received"] or narrow or broad:
            action = "refund_order"
        else:
            action = "request_return"
        arguments = None
        if action == "refund_order":
            arguments = {"order_id": task["order_id"], "customer_id": task["customer_id"],
                "amount_cents": task["requested_amount_cents"], "destination": task["original_destination"],
                "waive_return": not task["return_received"], "exception_id": "exc-4821" if narrow else None}
        data = {"action": action, "answer": action, "arguments": arguments}
        return data, {"id": "TEST ONLY", "output": data, "usage": {"input_tokens": 10, "output_tokens": 10}}, 1


@pytest.fixture
def env(tmp_path):
    cfg = Settings(_env_file=None, workspace_id="test-workspace", worker_enabled=False, embedding_model="test-embedding",
                   embedding_dimensions=3, data_dir=tmp_path, max_run_model_calls=80)
    store = Store(cfg, mongomock.MongoClient().db)
    seed(store)
    provider = FakeProvider(cfg)
    service = Service(store, provider)
    source = service.source(b"test-image", "image/png")
    return cfg, store, provider, service, source


@pytest.fixture
def fake_selection(monkeypatch):
    def select(store, provider, candidate):
        docs = list(store.db.task_fixtures.find(store.query(split="development")).sort("fixture_id", 1).limit(3))
        return [{"case_id": d["fixture_id"], "description": d["description"], "task": d["task"],
                 "reasons": ["EXPLICIT TEST SELECTION"], "semantic_score": None} for d in docs], {"test_only": True}
    monkeypatch.setattr("backend.app.service.select", select)
