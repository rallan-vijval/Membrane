"""Compact admission retains all paired evidence and caps generation time."""
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
from backend.app.common import Problem
from backend.app.provider import Provider
from backend.app.config import Settings
from backend.tests.test_lifecycle import stage, execute
from backend.app.runner import Worker


def test_concurrent_pairs_keep_exact_usage_and_twelve_unique_results(env, fake_selection):
    _, store, provider, service, _ = env
    original = provider.decide
    lock = threading.Lock()
    active = 0
    peak = 0
    def slow(task, memories, reserve, deadline=None):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            assert 0 < deadline - time.monotonic() <= 8
            time.sleep(0.025)
            return original(task, memories, reserve)
        finally:
            with lock:
                active -= 1
    provider.decide = slow
    run = execute(env, stage(env, True))
    assert peak == 2
    assert run['progress'] == {'completed': 12, 'total': 12}
    assert run['usage']['model_calls'] == run['summary']['calls'] == 12
    assert len(run['selection']) == 3
    assert all(len(case['executions']) == 4 for case in run['cases'])
    assert run['admission'] == 'eligible'


def test_expired_budget_sends_no_requests_and_never_approves(env, fake_selection):
    _, store, provider, service, _ = env
    candidate = stage(env, True)
    run_id = service.create_run(candidate['candidate_id'])['run_id']
    store.db.evaluation_runs.update_one(store.query(run_id=run_id), {'$set': {
        'created_at': (datetime.now(timezone.utc) - timedelta(seconds=31)).isoformat()}})
    worker = Worker(service)
    worker.execute(worker.claim())
    run = worker.detail(run_id)
    assert not provider.calls
    assert run['admission'] == 'inconclusive'
    assert run['progress']['completed'] == 12
    assert all(e['error'] == 'evaluation_timeout' for c in run['cases'] for e in c['executions'])
    with pytest.raises(Problem):
        service.decide(candidate['candidate_id'], 'timeout-approval', 'approve', 'test', run_id)


def test_older_suite_cannot_approve_even_if_its_summary_is_eligible(env, fake_selection):
    _, store, _, service, _ = env
    candidate = stage(env, True)
    run = execute(env, candidate)
    store.db.evaluation_runs.update_one(store.query(run_id=run['run_id']), {'$set': {'suite_version': 'older'}})
    with pytest.raises(Problem, match='exact current'):
        service.decide(candidate['candidate_id'], 'old-suite-approval', 'approve', 'test', run['run_id'])


def test_generation_deadline_limits_timeout_output_and_disables_retry():
    from types import SimpleNamespace
    import httpx
    import openai
    provider = Provider(Settings(_env_file=None))
    requests = []
    def fail(**kwargs):
        requests.append(kwargs)
        raise openai.APITimeoutError(request=httpx.Request('POST', 'https://example.invalid'))
    provider._client = SimpleNamespace(responses=SimpleNamespace(create=fail))
    with pytest.raises(Problem, match='no automatic retry'):
        provider.decide({}, [], lambda: None, deadline=time.monotonic() + 1)
    assert len(requests) == 1
    assert 0 < requests[0]['timeout'] <= 1
    assert requests[0]['max_output_tokens'] == 400
