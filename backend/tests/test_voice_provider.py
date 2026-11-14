from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from backend.app.common import Problem
from backend.app.models import AudioIn
from backend.app.provider import Provider
from backend.app.voice import Voice
from test_lifecycle import stage, execute


def test_exact_audio_text_cached_without_review_mutation(env, fake_selection, monkeypatch):
    cfg, store, provider, service, _ = env
    candidate = stage(env, True)
    run = execute(env, candidate)
    cfg.voice_enabled = True
    cfg.elevenlabs_api_key = SecretStr("TEST_SECRET_DO_NOT_LOG")
    cfg.elevenlabs_voice_id = "synthetic-test-voice"
    requests = []
    class Client:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, url, **kwargs):
            requests.append(kwargs["json"])
            return SimpleNamespace(content=b"TEST_MP3", headers={"request-id": "synthetic-request"}, raise_for_status=lambda: None)
    monkeypatch.setattr("backend.app.voice.httpx.Client", Client)
    voice = Voice(service)
    body = AudioIn(side="candidate", repetition=1)
    case = run["cases"][0]
    first = voice.create(run["run_id"], case["case_id"], body)
    again = voice.create(run["run_id"], case["case_id"], body)
    assert not first["cached"] and again["cached"]
    expected = next(e["attempt"]["answer"] for e in case["executions"] if e["side"] == "candidate" and e["repetition"] == 1)
    assert requests[0]["text"] == first["transcript"] == expected
    assert len(requests) == 1
    assert store.active()["memories"] == []
    assert store.get("memory_candidates", "candidate_id", candidate["candidate_id"])["status"] == "eligible"
    # Same shared synthesis settings apply to either side.
    baseline = voice.create(run["run_id"], case["case_id"], AudioIn(side="baseline", repetition=1))
    assert baseline["transcript"]
    if len(requests) == 2:
        assert requests[0]["voice_settings"] == requests[1]["voice_settings"]


def test_voice_disabled_missing_or_excessive_text_never_calls_provider(env, fake_selection):
    cfg, store, provider, service, _ = env
    voice = Voice(service)
    with pytest.raises(Problem, match="Configure"):
        voice.create("missing", "missing", AudioIn(side="baseline", repetition=1))
    candidate = stage(env, True)
    run = execute(env, candidate)
    cfg.voice_enabled, cfg.elevenlabs_api_key, cfg.elevenlabs_voice_id = True, SecretStr("test"), "test"
    cfg.max_tts_characters_per_request = 1
    with pytest.raises(Problem, match="length limit"):
        voice.create(run["run_id"], run["cases"][0]["case_id"], AudioIn(side="baseline", repetition=1))


def test_provider_malformed_and_incomplete_response_preserved(env):
    cfg, *_ = env
    cfg.agent_model = "test-model"
    cfg.openai_api_key = SecretStr("TEST_ONLY")
    provider = Provider(cfg)
    raw = {"id": "TEST_ONLY", "status": "completed", "output": [{"malformed": "evidence"}], "usage": {"input_tokens": 7}}
    response = SimpleNamespace(status="completed", output_text="not json", model_dump=lambda **kwargs: raw)
    provider._client = SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs: response))
    reserved = []
    data, stored, calls = provider.decide({"synthetic": True}, [], lambda: reserved.append(1))
    assert data is None and stored == raw and calls == len(reserved) == 1
    response.status = "incomplete"
    data, stored, calls = provider.decide({}, [], lambda: reserved.append(1))
    assert data is None and stored == raw


def test_malformed_attempt_is_inconclusive_but_raw_response_survives(env, fake_selection):
    cfg, store, provider, service, _ = env
    original = provider.decide
    def malformed(task, memories, reserve):
        data, raw, calls = original(task, memories, reserve)
        return None, raw, calls
    provider.decide = malformed
    run = execute(env, stage(env, True))
    assert run["admission"] == "inconclusive"
    assert all(e["raw_responses"] and e["error"] for c in run["cases"] for e in c["executions"])
    assert run["summary"]["input_tokens"] == 480


def test_config_change_on_restart_cannot_pass(env, fake_selection):
    from backend.app.runner import Worker
    cfg, store, provider, service, _ = env
    candidate = stage(env, True)
    run_id = service.create_run(candidate["candidate_id"])["run_id"]
    original = provider.config
    provider.config = lambda: {**original(), "changed": True}
    worker = Worker(service)
    worker.execute(worker.claim())
    assert worker.detail(run_id)["admission"] == "inconclusive"
    assert len(provider.calls) == 0


def test_interrupted_suite_preparation_recovers(env, fake_selection):
    cfg, store, provider, service, _ = env
    candidate = stage(env, True)
    run_id = service.create_run(candidate["candidate_id"])["run_id"]
    store.db.evaluation_runs.update_one(store.query(run_id=run_id), {"$set": {"selection": [], "created_at": "2000-01-01T00:00:00+00:00"}})
    service.reconcile()
    assert store.get("evaluation_runs", "run_id", run_id)["admission"] == "inconclusive"
    assert store.get("memory_candidates", "candidate_id", candidate["candidate_id"])["status"] == "inconclusive"
