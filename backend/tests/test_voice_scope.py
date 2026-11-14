"""Explicit fakes; these tests never call ElevenLabs or model services."""
from io import BytesIO
from datetime import datetime, timedelta, timezone
import wave
import mongomock
import pytest
from pydantic import SecretStr
from fastapi.testclient import TestClient
from backend.app.audio_sources import AudioSources
from backend.app.common import Problem, now
from backend.app.models import ScopeExperimentIn
from backend.app.scope_experiments import ScopeExperiments, scenarios
from backend.app.main import create_app
from test_governed_memory import governed, stage

@pytest.fixture
def audio(env, monkeypatch):
    cfg, store, provider, service, _ = env
    cfg.transcription_enabled = True
    cfg.elevenlabs_api_key = SecretStr('TEST_ONLY_KEY')
    component = AudioSources(service)
    calls = []
    monkeypatch.setattr(component, 'normalize', lambda data: (b'normalized', 2.0))
    def transcribe(data):
        calls.append(data)
        return 'Order 4821 only', [{'text': 'Order', 'start': 0., 'end': 0.5}], 'en', 'TEST_REQUEST'
    monkeypatch.setattr(component, 'transcribe', transcribe)
    monkeypatch.setattr(provider, 'propose_from_text', lambda text: ({'quotation': text, 'proposed_text': 'Order exception',
        'proposed_scope': {'kind': 'order', 'order_id': '4821', 'customer_id': 'customer-4821', 'exception_id': 'exc-4821'}}, {'usage': {}}), raising=False)
    return component, calls

def test_audio_idempotency_budget_and_review_preserve_original(audio):
    a, calls = audio
    first = a.create(b'original-audio', 'key')
    assert first['status'] == 'transcribed'
    assert a.create(b'original-audio', 'key') == first
    assert len(calls) == 1
    with pytest.raises(Problem, match='another upload'):
        a.create(b'different', 'key')
    source = a.review(first['audio_source_id'], 'Corrected order 4821 only', 'review')
    assert source['source_kind'] == 'audio' and source['image_url'] is None
    assert source['extracted_text'] == 'Corrected order 4821 only'
    assert source['provenance']['original_transcript'] == 'Order 4821 only'
    assert source['trust'] == 'untrusted'
    assert a.review(first['audio_source_id'], 'Corrected order 4821 only', 'review') == source
    with pytest.raises(Problem): a.review(first['audio_source_id'], 'different', 'review')
    assert a.store.db.trusted_exceptions.count_documents(a.store.query()) == 1
    assert a.store.db.memory_candidates.count_documents(a.store.query()) == 0
    assert a.store.get('workspace_state', 'workspace_id', a.store.workspace)['transcription_seconds'] == 2

def test_budget_failure_and_provider_timeout_never_retry_automatically(audio, monkeypatch):
    a, calls = audio
    a.store.settings.max_transcription_seconds_total = 1
    assert a.create(b'a', 'budget')['error'] == 'transcription_budget'
    assert calls == []
    a.store.settings.max_transcription_seconds_total = 600
    def timeout(data):
        calls.append(data)
        raise TimeoutError('SECRET MUST NOT LEAK')
    monkeypatch.setattr(a, 'transcribe', timeout)
    failed = a.create(b'b', 'timeout')
    assert failed['error'] == 'transcription_failed' and 'SECRET' not in str(failed)
    assert a.create(b'b', 'timeout')['status'] == 'failed' and len(calls) == 1
    with pytest.raises(Problem): a.review(failed['audio_source_id'], 'text', 'review')

def test_audio_busy_missing_key_and_cross_workspace(audio):
    a, _ = audio
    assert a.semaphore.acquire(False)
    with pytest.raises(Problem) as error: a.create(b'a', 'busy')
    assert error.value.status == 429
    a.semaphore.release()
    doc = a.create(b'a', 'ok')
    a.store.workspace = 'other-workspace'
    with pytest.raises(Problem): a.get(doc['audio_source_id'])
    a.store.settings.transcription_enabled = False
    with pytest.raises(Problem) as error: a.create(b'a', 'disabled')
    assert error.value.status == 503

def test_real_audio_validation_and_normalization(env):
    a = AudioSources(env[3])
    stream = BytesIO()
    with wave.open(stream, 'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(16000); f.writeframes(b'\x00\x00' * 16000)
    wav, duration = a.normalize(stream.getvalue())
    assert wav.startswith(b'RIFF') and duration == 1
    with pytest.raises(Problem): a.normalize(b'not-audio')
    a.store.settings.max_audio_seconds = 1
    with wave.open(stream := BytesIO(), 'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(16000); f.writeframes(b'\x00\x00' * 32000)
    with pytest.raises(Problem): a.normalize(stream.getvalue())
    with pytest.raises(Problem): a.normalize(b'x' * (a.store.settings.max_audio_bytes+1))

def test_audio_http_access_and_review(audio):
    a, _ = audio
    app = create_app(a.store.settings, a.store, a.service.provider)
    app.state.audio_sources.normalize = a.normalize
    app.state.audio_sources.transcribe = a.transcribe
    with TestClient(app) as c:
        assert c.post('/api/audio-sources', files={'file': ('a.wav', b'test')}).status_code == 422
        r = c.post('/api/audio-sources', headers={'Idempotency-Key': 'http'}, files={'file': ('a.wav', b'test')})
        assert r.status_code == 201, r.text
        doc = r.json()
        assert c.get(doc['audio_url']).content == b'normalized'
        reviewed = c.post('/api/audio-sources/'+doc['audio_source_id']+'/review', headers={'Idempotency-Key': 'review-http'}, json={'reviewed_text': 'Reviewed note'})
        assert reviewed.status_code == 201, reviewed.text
        assert reviewed.json()['source_kind'] == 'audio'
        assert c.get('/api/health').json()['transcription']['status'] in ('degraded','unavailable')

def test_scope_scenarios_preserve_originals_and_expire_only_copy(governed):
    cfg, s, p, e, service, source = governed
    task = s.get(cfg.fixture_collection, 'fixture_id', 'development-01')['task']
    policy = service.policy_snapshot()
    before = repr((task, policy))
    cases = scenarios(task, policy, now())
    assert len(cases) == 7 and len({c['fixture_hash'] for c in cases}) == 7
    assert repr((task, policy)) == before
    assert cases[0]['expected_action'] == 'refund_order'
    assert cases[2]['expected_action'] == 'request_verification'
    assert cases[-1]['policy_snapshot']['exceptions'][0]['expires_at'] != policy['exceptions'][0]['expires_at']
    assert all(c['changed_fields'] for c in cases[1:])

def test_scope_worker_isolated_idempotent_and_recoverable(governed):
    cfg, s, p, e, service, source = governed
    candidate = stage(governed)
    worker = ScopeExperiments(service)
    body = ScopeExperimentIn(base_version_id=s.active()['version_id'])
    accepted = worker.create(candidate['candidate_id'], body, 'key')
    assert worker.create(candidate['candidate_id'], body, 'key') == accepted
    prior = s.get('memory_candidates', 'candidate_id', candidate['candidate_id'])
    active = s.active()
    job = worker.claim()
    # Simulate stopping after four persisted decisions, then resuming its expired lease.
    original = p.decide
    def partial(*args):
        r = original(*args)
        if len(p.calls) == 4: worker.stop_event.set()
        return r
    p.decide = partial
    worker.execute(job)
    assert s.db.scope_results.count_documents(s.query()) == 4
    s.db.scope_experiments.update_one(s.query(experiment_id=job['experiment_id']), {'$set': {'lease_until': '2000-01-01T00:00:00+00:00'}})
    p.decide = original
    resumed = ScopeExperiments(service)
    resumed.execute(resumed.claim())
    result = resumed.detail(job['experiment_id'])
    assert result['progress'] == {'completed': 28, 'total': 28}
    assert result['usage']['model_calls'] == 28
    assert result['admission_evidence'] is False
    assert len(result['cases']) == 7
    assert len(p.calls) == 28
    assert s.active() == active
    assert s.get('memory_candidates', 'candidate_id', candidate['candidate_id']) == prior
    s.workspace = 'other-workspace'
    with pytest.raises(Problem): resumed.detail(job['experiment_id'])

def test_scope_budget_and_stale_base(governed):
    cfg, s, p, e, service, source = governed
    candidate = stage(governed)
    worker = ScopeExperiments(service)
    with pytest.raises(Problem): worker.create(candidate['candidate_id'], ScopeExperimentIn(base_version_id='stale'), 'stale')
    accepted = worker.create(candidate['candidate_id'], ScopeExperimentIn(base_version_id=s.active()['version_id']), 'valid')
    s.db.scope_experiments.update_one(s.query(experiment_id=accepted['experiment_id']), {'$set': {'usage.model_calls': 56}})
    worker.execute(worker.claim())
    doc = worker.detail(accepted['experiment_id'])
    assert doc['status'] == 'inconclusive' and doc['usage']['model_calls'] == 56
    assert p.calls == []
    assert all(e['error'] for c in doc['cases'] for e in c['executions'])

@pytest.mark.parametrize('status,code', [(401, 'transcription_authentication'), (403, 'transcription_permission'), (402, 'transcription_credits'), (429, 'transcription_rate_limit')])
def test_provider_rejections_are_actionable_and_redacted(audio, monkeypatch, status, code):
    import httpx
    a, _ = audio
    def rejected(data):
        response = httpx.Response(status, request=httpx.Request('POST', 'https://example.invalid'), text='SECRET')
        raise httpx.HTTPStatusError('SECRET', request=response.request, response=response)
    monkeypatch.setattr(a, 'transcribe', rejected)
    result = a.create(b'a', str(status))
    assert result['error'] == code and 'SECRET' not in str(result)

def test_speech_provider_receives_bounded_explicit_parameters(audio, monkeypatch):
    from types import SimpleNamespace
    from backend.app import audio_sources
    a, _ = audio
    # Call the real wrapper, replacing only its HTTP transport.
    requests = []
    class Client:
        def __init__(self, **kwargs): assert kwargs['timeout'] == 90
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            requests.append((url, kwargs))
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {'text': 'Hello', 'words': [{'type': 'word', 'text': 'Hello', 'start': 0, 'end': 1}], 'language_code': 'en'}, headers={})
    monkeypatch.setattr(audio_sources.httpx, 'Client', Client)
    text, words, language, _ = AudioSources.transcribe(a, b'wav')
    assert text == 'Hello' and language == 'en'
    url, kwargs = requests[0]
    assert url == 'https://api.elevenlabs.io/v1/speech-to-text'
    assert kwargs['data'] == {'model_id': 'scribe_v2', 'timestamps_granularity': 'word', 'diarize': 'false', 'tag_audio_events': 'false', 'webhook': 'false'}
    assert kwargs['files']['file'][1] == b'wav'

def test_reviewed_transcript_must_have_an_exact_quote(env, monkeypatch):
    from backend.app.provider import Provider
    p = Provider(env[0])
    output = {'extracted_text': 'invented', 'quotation': 'not in original', 'proposed_text': 'new rule',
              'proposed_scope': {'kind': 'global', 'order_id': None, 'customer_id': None, 'exception_id': None}}
    monkeypatch.setattr(p, '_response', lambda *args: (output, {'usage': {}}, 1))
    with pytest.raises(Problem): p.propose_from_text('actual reviewed transcript')
    output['quotation'] = 'reviewed transcript'
    assert p.propose_from_text('actual reviewed transcript')[0]['proposed_text'] == 'new rule'

def test_scope_preparation_failure_is_saved_and_not_retried(governed, monkeypatch):
    cfg, s, p, e, service, source = governed
    candidate = stage(governed)
    attempts = []
    def fail(*args):
        attempts.append(1)
        raise Problem('search_unavailable', 'Synthetic test failure', 503)
    monkeypatch.setattr(service.memory, 'retrieve', fail)
    worker = ScopeExperiments(service)
    body = ScopeExperimentIn(base_version_id=s.active()['version_id'])
    accepted = worker.create(candidate['candidate_id'], body, 'prepare')
    assert worker.create(candidate['candidate_id'], body, 'prepare') == accepted
    result = worker.detail(accepted['experiment_id'])
    assert result['status'] == 'failed' and result['error'] == 'search_unavailable'
    assert len(attempts) == 1 and worker.claim() is None

def test_scope_repeated_action_variation_is_inconclusive(governed):
    cfg, s, p, e, service, source = governed
    candidate = stage(governed)
    worker = ScopeExperiments(service)
    job_id = worker.create(candidate['candidate_id'], ScopeExperimentIn(base_version_id=s.active()['version_id']), 'variance')['experiment_id']
    worker.execute(worker.claim())
    # Differing wording alone is not a behavior change.
    q = s.query(experiment_id=job_id, case_id='other-order', side='baseline', repetition=2)
    s.db.scope_results.update_one(q, {'$set': {'attempt.answer': 'Same action, different wording'}})
    case = next(c for c in worker.detail(job_id)['cases'] if c['case_id'] == 'other-order')
    assert case['repetition_consistent']
    s.db.scope_results.update_one(q, {'$set': {'attempt.action': 'answer'}})
    case = next(c for c in worker.detail(job_id)['cases'] if c['case_id'] == 'other-order')
    assert not case['repetition_consistent'] and case['classification'] == 'inconclusive'

def test_webm_recording_without_duration_is_measured_after_decode(env):
    import subprocess
    a = AudioSources(env[3])
    stream = BytesIO()
    with wave.open(stream, 'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(16000); f.writeframes(b'\x00\x00' * 16000)
    # Pipe output matches MediaRecorder's nonseekable WebM container, often without format duration.
    webm = subprocess.run(['ffmpeg', '-v', 'error', '-i', 'pipe:0', '-c:a', 'libopus', '-f', 'webm', 'pipe:1'], input=stream.getvalue(), capture_output=True, check=True, timeout=10).stdout
    wav, duration = a.normalize(webm)
    assert wav.startswith(b'RIFF') and 0.9 <= duration <= 1.1
