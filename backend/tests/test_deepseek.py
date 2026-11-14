import json
from types import SimpleNamespace

import httpx
import openai
import pytest
from pydantic import SecretStr

from backend.app.common import Problem
from backend.app.config import Settings
from backend.app.provider import DECISION_SCHEMA, Provider


def response(data=None, status="completed"):
    data = data or {"action": "request_return", "answer": "Return required.", "arguments": None}
    raw = {"id": "SYNTHETIC-DEEPSEEK-RESPONSE", "status": status, "output": data,
           "usage": {"input_tokens": 4, "output_tokens": 6}}
    return SimpleNamespace(status=status, output_text=json.dumps(data), model_dump=lambda **kw: raw)


def test_deepseek_uses_own_key_base_url_schema_and_disabled_thinking(monkeypatch):
    cfg = Settings(_env_file=None, deepseek_api_key="DEEPSEEK_TEST_SECRET", openai_api_key="UNUSED_OPENAI_SECRET")
    captured = []
    def factory(**kwargs):
        captured.append(kwargs)
        def create(**params):
            captured.append(params)
            return response()
        return SimpleNamespace(responses=SimpleNamespace(create=create))
    monkeypatch.setattr("backend.app.provider.OpenAI", factory)
    provider = Provider(cfg)
    reservations = []
    data, raw, count = provider.decide({"message": "refund", "positive_obligation": True}, [], lambda: reservations.append(1))
    assert captured[0]["api_key"] == "DEEPSEEK_TEST_SECRET"
    assert captured[0]["base_url"] == "https://api.deepseek.com"
    assert captured[0]["max_retries"] == 0
    request = captured[1]
    assert request["model"] == "deepseek-flash"
    assert request["text"]["format"]["schema"] == DECISION_SCHEMA
    assert "strict" not in request["text"]["format"]
    assert request["reasoning"] == {"effort": "none"}
    assert "positive_obligation" not in str(request["input"])
    assert count == len(reservations) == 1
    assert provider.config()["provider"] == "deepseek"
    assert "SECRET" not in str(provider.config())


def test_deepseek_image_input_uses_same_provider_key(monkeypatch):
    cfg = Settings(_env_file=None, deepseek_api_key="TEST")
    provider = Provider(cfg)
    requests = []
    extracted = {"extracted_text": "Order 4821 only", "quotation": "Order 4821 only", "proposed_text": "Scoped rule",
        "proposed_scope": {"kind": "order", "order_id": "4821", "customer_id": "customer-4821", "exception_id": "exc-4821"}}
    def create(**kwargs):
        requests.append(kwargs)
        return response(extracted)
    provider._client = SimpleNamespace(responses=SimpleNamespace(create=create))
    data, provenance = provider.extract(b"SYNTHETIC_IMAGE_BYTES", "image/png")
    assert requests[0]["input"][0]["content"][1]["image_url"].startswith("data:image/png;base64,")
    assert provenance["provider"] == "deepseek"
    assert data["proposed_scope"]["exception_id"] == "exc-4821"


def test_json_or_whitespace_failure_preserved_without_selective_retry():
    cfg = Settings(_env_file=None, deepseek_api_key="TEST")
    provider = Provider(cfg)
    attempts = []
    raw = {"id": "SYNTHETIC-RAW-WHITESPACE", "output": "  "}
    def create(**kwargs):
        attempts.append(kwargs)
        return SimpleNamespace(status="completed", output_text="  ", model_dump=lambda **kw: raw)
    provider._client = SimpleNamespace(responses=SimpleNamespace(create=create))
    data, evidence, calls = provider.decide({}, [], lambda: None)
    assert data is None and evidence == raw and calls == len(attempts) == 1


def test_transient_retry_counts_each_request_and_does_not_retry_validation(monkeypatch):
    cfg = Settings(_env_file=None, deepseek_api_key="TEST")
    provider = Provider(cfg)
    attempts, reservations = [], []
    def create(**kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise openai.APIConnectionError(request=httpx.Request("POST", "https://api.deepseek.com/responses"))
        return response()
    monkeypatch.setattr("backend.app.provider.time.sleep", lambda seconds: None)
    provider._client = SimpleNamespace(responses=SimpleNamespace(create=create))
    data, evidence, calls = provider.decide({}, [], lambda: reservations.append(1))
    assert calls == len(attempts) == len(reservations) == 2


def test_missing_deepseek_key_has_no_openai_fallback():
    cfg = Settings(_env_file=None, deepseek_api_key="", openai_api_key="UNUSED")
    with pytest.raises(Problem, match="DEEPSEEK_API_KEY"):
        Provider(cfg).decide({}, [], lambda: None)


def test_openai_remains_explicit_option_with_strict_format():
    cfg = Settings(_env_file=None, llm_provider="openai", vision_provider="openai", openai_api_key="TEST", agent_model="TEST_MODEL")
    provider = Provider(cfg)
    requests = []
    def create(**kwargs):
        requests.append(kwargs)
        return response()
    provider._client = SimpleNamespace(responses=SimpleNamespace(create=create))
    provider.decide({}, [], lambda: None)
    assert requests[0]["text"]["format"]["strict"] is True
    assert "reasoning" not in requests[0]


def test_extraction_rejects_unverified_authority_fields():
    cfg = Settings(_env_file=None, deepseek_api_key="TEST")
    provider = Provider(cfg)
    bad = {"extracted_text": "text", "quotation": "text", "proposed_text": "rule",
           "proposed_scope": {"kind": "global", "exception_id": "invented"}}
    provider._client = SimpleNamespace(responses=SimpleNamespace(create=lambda **kw: response(bad)))
    with pytest.raises(Problem, match="local schema"):
        provider.extract(b"SYNTHETIC", "image/png")
