"""Explicit live lab checks. Never approve or activate memory; provider calls are billable."""
import argparse
import json
import time
from pathlib import Path
from uuid import uuid4
import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--candidate-id', help='Start a new 28-decision scope experiment')
    group.add_argument('--experiment-id', help='Inspect/wait for an existing experiment, without starting another')
    group.add_argument('--audio', type=Path, help='Transcribe a short synthetic audio file; transcript review stays manual')
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=120) as client:
        def call(method, path, **kw):
            response = client.request(method, path, **kw)
            if not response.is_success:
                try: code = response.json().get('error', {}).get('code', 'http_error')
                except Exception: code = 'http_error'
                raise RuntimeError(f'HTTP {response.status_code}: {code}')
            return response.json()
        if args.audio:
            if args.audio.stat().st_size > 10 * 1024 * 1024:
                raise RuntimeError('Audio exceeds 10 MiB')
            with args.audio.open('rb') as stream:
                doc = call('POST', '/api/audio-sources', headers={'Idempotency-Key': uuid4().hex}, files={'file': (args.audio.name, stream)})
            print(json.dumps({k: doc.get(k) for k in ('audio_source_id', 'status', 'duration_seconds', 'error', 'model')}, indent=2))
            if doc['status'] != 'transcribed': return 1
            print('Transcript retained for explicit reviewer confirmation. No candidate created.')
            return 0
        active_before = call('GET', '/api/memory/active')['version_id']
        if args.candidate_id:
            candidate = call('GET', '/api/candidates/'+args.candidate_id)
            experiment_id = call('POST', '/api/candidates/'+args.candidate_id+'/experiments/scope',
                headers={'Idempotency-Key': uuid4().hex}, json={'base_version_id': active_before})['experiment_id']
        else:
            experiment_id = args.experiment_id
            candidate_id = call('GET', '/api/experiments/'+experiment_id)['candidate_id']
            candidate = call('GET', '/api/candidates/'+candidate_id)
        deadline = time.monotonic() + 900
        last_progress = None
        while time.monotonic() < deadline:
            result = call('GET', '/api/experiments/'+experiment_id)
            progress = result['progress']['completed']
            if progress != last_progress:
                print(f'{progress}/28 decisions recorded', flush=True)
                last_progress = progress
            if result['status'] not in ('queued', 'running'):
                break
            time.sleep(3)
        else: raise RuntimeError('Experiment did not finish within 900 seconds; inspect stored evidence')
        final_candidate = call('GET', '/api/candidates/'+candidate['candidate_id'])
        unchanged = final_candidate['status'] == candidate['status'] and final_candidate.get('latest_run_id') == candidate.get('latest_run_id')
        active_unchanged = call('GET', '/api/memory/active')['version_id'] == active_before
        report = dict(experiment_id=experiment_id, status=result['status'], progress=result['progress'],
            admission_evidence=result['admission_evidence'], model_calls=result['usage']['model_calls'],
            classifications={case['case_id']: case['classification'] for case in result['cases']},
            candidate_admission_unchanged=unchanged, active_version_unchanged=active_unchanged)
        print(json.dumps(report, indent=2))
        return 0 if result['progress']['completed'] == 28 and not result['admission_evidence'] and unchanged and active_unchanged else 1

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit('Lab check failed. Inspect redacted API status and stored evidence; credentials and provider details omitted.')
