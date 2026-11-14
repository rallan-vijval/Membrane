from types import SimpleNamespace as NS
from threading import BoundedSemaphore
import pytest
from backend.app.integrations.api import EmbeddingConfig, IntegrationFailure, create_embedding_client, probe_provider, TracerConfig, create_tracer

def client(provider="voyage", retries=1):
    return create_embedding_client(EmbeddingConfig(provider, "test-model", 3, "secret-test", max_retries=retries), BoundedSemaphore(1))

@pytest.mark.parametrize("provider", ["openai", "voyage"])
def test_sync_provider_contract(provider):
    c = client(provider)
    calls = []
    def request(**kwargs):
        calls.append(kwargs)
        return NS(embeddings=[[1., 0., 0.]], total_tokens=2, data=[NS(index=0, embedding=[1., 0., 0.])], usage=NS(total_tokens=2))
    c.sdk = NS(embed=request, embeddings=NS(create=request))
    batch = c.embed_documents(["test"])
    assert batch.profile_id == c.describe()["profile_id"]
    assert batch.attempted_calls == 1 and batch.input_tokens == 2
    c.embed_query("test")
    assert len(calls) == 2
    if provider == "voyage":
        assert [x["input_type"] for x in calls] == ["document", "query"]
        assert calls[0]["truncation"] is False and calls[0]["output_dimension"] == 3
    else:
        assert calls[0]["dimensions"] == 3

def test_retry_fresh_call_and_sanitized_error():
    c = client()
    calls = []
    class RateLimit(Exception):
        status_code = 429
    def request(*args):
        calls.append(1)
        raise RateLimit("secret-test private document")
    c._request = request
    with pytest.raises(IntegrationFailure) as error:
        c.embed_query("test")
    assert len(calls) == error.value.attempted_calls == 2
    assert "secret-test" not in str(error.value)

def test_malformed_response_no_retry():
    c = client()
    c._request = lambda *args: ([[float("nan"), 0, 0]], 1)
    with pytest.raises(IntegrationFailure) as error:
        c.embed_query("test")
    assert error.value.code == "invalid_response" and error.value.attempted_calls == 1

def test_invalid_inputs_and_redacted_configuration():
    c = client()
    assert "secret-test" not in repr(c.config)
    with pytest.raises(IntegrationFailure) as error:
        c.embed_documents([])
    assert error.value.attempted_calls == 0
    assert "secret-test" not in repr(TracerConfig(True, "secret-test"))
    with create_tracer(TracerConfig()).span("test") as span:
        assert span.trace_url is None

def test_probe_does_not_reacquire_semaphore(monkeypatch):
    c = client()
    c._request = lambda *args: ([[1, 0, 0]], 1)
    monkeypatch.setattr("backend.app.integrations.api.create_embedding_client", lambda *args: c)
    assert probe_provider(c.config, c.semaphore)["status"] == "ok"
