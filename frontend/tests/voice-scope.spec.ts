/** Synthetic HTTP fixtures; recording controls and feature state are exercised in Chrome. */
import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
const examples = JSON.parse(readFileSync(resolve('../contracts/examples.json'), 'utf8')).examples;
const screenshot = resolve('../fixtures/support-4821.png');
const voice = { audio_source_id: 'voice_test', created_at: '2026-11-14T17:00:00Z', status: 'transcribed', sha256: 'TEST', duration_seconds: 2,
  audio_url: '/api/audio-sources/voice_test/audio', transcript: 'Order 4821 only', words: [{ text: 'Order', start: 0, end: 0.5 }], model: 'scribe_v2', language: 'en', error: null, trust: 'untrusted' };

async function mock(page: Page) {
  const calls: { path: string; method: string; key?: string; body?: unknown }[] = [];
  let candidate: Record<string, unknown> | null = null;
  let reads = 0;
  const job = { experiment_id: 'experiment_test', candidate_id: 'candidate_voice_scope', created_at: '2026-11-14T17:00:00Z',
    status: 'completed', admission_evidence: false, candidate_hash: 'TEST_HASH', base_version_id: examples.active_version.version_id,
    profile_id: 'TEST_PROFILE', config: {}, evaluated_at: '2026-11-14T17:00:00Z', progress: { completed: 28, total: 28 }, usage: { model_calls: 28 },
    scenarios: ['Covered order', 'Other order', 'Other customer', 'Unverified owner', 'Redirected payment', 'Excess amount', 'Expired exception'].map((title, i) => ({
      scenario_id: String(i), title, changed_fields: { verified: { from: true, to: false } }, task: { verified: false }, policy_snapshot: {}, expected_action: 'request_verification', rule: 'Ownership must be verified', fixture_hash: 'TEST',
      retrieval: { case_id: String(i), retrieval_at: '2026-11-14T17:00:00Z', profile_id: 'TEST_PROFILE', base_version_id: examples.active_version.version_id, entries: [], usage: {} },
    })),
    cases: Array.from({ length: 7 }, (_, i) => ({ case_id: String(i), classification: 'unchanged-safe', repetition_consistent: true,
      executions: ['baseline', 'candidate'].flatMap(side => [1, 2].map(repetition => ({ side, repetition, raw_responses: [], error: null, input_hash: 'TEST', calls: 1, input_tokens: 1, output_tokens: 1, latency_ms: 1,
        attempt: { action: 'request_verification', answer: 'Please verify ownership.', arguments: null }, tool_outcome: null, checks: [{ code: 'ownership', passed: true, reason: 'Verified ownership required' }] }))) })),
  };
  await page.route('http://127.0.0.1:5173/api/**', async route => {
    const r = route.request(); const path = new URL(r.url()).pathname; const method = r.method();
    calls.push({ path, method, key: r.headers()['idempotency-key'], body: method === 'POST' && r.headers()['content-type']?.includes('application/json') ? r.postDataJSON() : undefined });
    if (path === '/api/health') return route.fulfill({ json: examples.health_unconfigured });
    if (path === '/api/memory/active') return route.fulfill({ json: examples.active_version });
    if (path === '/api/history') return route.fulfill({ json: { versions: [], events: [], truncated: false } });
    if (path === '/api/memory/entries') return route.fulfill({ json: { version_id: examples.active_version.version_id, evaluated_at: '2026-11-14T17:00:00Z', items: [], truncated: false } });
    if (path === '/api/tasks') return route.fulfill({ json: { items: [], truncated: false } });
    if (path === '/api/audio-sources' || path === '/api/audio-sources/voice_test') return route.fulfill({ status: method === 'POST' ? 201 : 200, json: voice });
    if (path.endsWith('/review')) return route.fulfill({ status: 201, json: { ...examples.source, source_kind: 'audio', image_url: null, audio_url: voice.audio_url, audio_source_id: voice.audio_source_id,
      extracted_text: 'Corrected order 4821 only', proposed_text: 'Order 4821 exception only', provenance: { model: 'TEST', original_transcript: voice.transcript } } });
    if (path.endsWith('/audio')) return route.fulfill({ contentType: 'audio/wav', body: Buffer.alloc(44) });
    if (path.startsWith('/api/sources')) return route.fulfill({ status: method === 'POST' ? 201 : 200, json: examples.source });
    if (path === '/api/candidates' && method === 'GET') return route.fulfill({ json: { items: candidate ? [candidate] : [], truncated: false } });
    if (path === '/api/candidates') { candidate = { ...examples.candidate_staged, ...r.postDataJSON(), candidate_id: 'candidate_voice_scope' }; return route.fulfill({ status: 201, json: candidate }); }
    if (path.endsWith('/experiments/scope')) return route.fulfill({ status: 202, json: { experiment_id: job.experiment_id } });
    if (path === '/api/experiments/experiment_test') { reads++; return route.fulfill({ json: reads === 1 ? { ...job, status: 'queued', progress: { completed: 0, total: 28 }, cases: [] } : job }); }
    if (path.startsWith('/api/candidates/')) return route.fulfill({ json: candidate });
    return route.fulfill({ status: 404, json: { error: { code: 'not_found', message: 'Not found' } } });
  });
  return calls;
}

test('audio transcript must be explicitly reviewed before proposing, and never auto-stages memory', async ({ page }) => {
  const calls = await mock(page);
  await page.goto('/');
  await page.getByText('Use a voice note instead', { exact: true }).click();
  await page.getByLabel('Audio source file').setInputFiles({ name: 'note.wav', mimeType: 'audio/wav', buffer: Buffer.alloc(44) });
  expect(calls.some(c => c.path === '/api/audio-sources')).toBe(false);
  await page.getByRole('button', { name: 'Transcribe audio', exact: true }).click();
  await expect(page.getByLabel('Reviewed transcript')).toHaveValue('Order 4821 only');
  expect(calls.some(c => c.path.endsWith('/review'))).toBe(false);
  await page.getByLabel('Reviewed transcript').fill('Corrected order 4821 only');
  await page.getByRole('button', { name: 'Confirm transcript and propose a memory' }).click();
  await expect(page.getByRole('textbox', { name: 'Proposed memory', exact: true })).toHaveValue('Order 4821 exception only');
  await expect(page.getByLabel('Reviewed voice source')).toBeVisible();
  expect(calls.find(c => c.path.endsWith('/review'))?.body).toEqual({ reviewed_text: 'Corrected order 4821 only' });
  expect(calls.filter(c => c.method === 'POST').every(c => !!c.key)).toBe(true);
  expect(calls.some(c => c.path === '/api/candidates')).toBe(false);
});

test('microphone denial leaves file upload available without sending audio', async ({ page }) => {
  const calls = await mock(page);
  await page.addInitScript(() => Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia: () => Promise.reject(new DOMException('Denied', 'NotAllowedError')) } }));
  await page.goto('/');
  await page.getByText('Use a voice note instead', { exact: true }).click();
  await page.getByRole('button', { name: 'Record a voice note' }).click();
  await expect(page.getByText('Microphone access was denied or unavailable. You can upload a saved clip instead.')).toBeVisible();
  await expect(page.getByLabel('Audio source file')).toBeEnabled();
  expect(calls.some(c => c.path === '/api/audio-sources')).toBe(false);
});

test('cancelling recording releases the microphone and discards the clip', async ({ page }) => {
  const calls = await mock(page);
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia: async () => ({ getTracks: () => [{ stop() {} }] }) } });
    class Recorder {
      static isTypeSupported() { return true; }
      state = 'inactive'; mimeType = 'audio/webm';
      ondataavailable: ((e: { data: Blob }) => void) | null = null;
      onstop: (() => void) | null = null;
      onerror: (() => void) | null = null;
      start() { this.state = 'recording'; }
      stop() { this.state = 'inactive'; queueMicrotask(() => { this.ondataavailable?.({ data: new Blob(['TEST']) }); this.onstop?.(); }); }
    }
    window.MediaRecorder = Recorder as unknown as typeof MediaRecorder;
  });
  await page.goto('/');
  await page.getByText('Use a voice note instead', { exact: true }).click();
  await page.getByRole('button', { name: 'Record a voice note' }).click();
  await expect(page.getByRole('button', { name: 'Stop recording', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Cancel recording' }).click();
  await expect(page.getByRole('button', { name: 'Transcribe audio', exact: true })).toBeDisabled();
  await expect(page.getByLabel('Selected audio playback')).toHaveCount(0);
  expect(calls.some(c => c.path === '/api/audio-sources')).toBe(false);
});

test('scope experiment polls and reloads evidence without unlocking approval or generating another run', async ({ page }) => {
  const calls = await mock(page);
  await page.goto('/');
  await page.getByLabel('Source file (image, PDF, text or video; synthetic data only)').setInputFiles(screenshot);
  await page.getByRole('button', { name: 'Save for testing', exact: true }).click();
  await page.getByRole('button', { name: 'Dashboard', exact: true }).click();
  await page.getByRole('button', { name: 'Scope experiments', exact: true }).click();
  await page.getByRole('button', { name: /Explore this memory/ }).click();
  await expect(page.getByText('Exploratory experiment: completed', { exact: false })).toBeVisible({ timeout: 10000 });
  await page.getByText('Unverified owner - unchanged-safe', { exact: true }).click();
  await expect(page.locator('.scope-scenario').filter({ has: page.getByText('Unverified owner - unchanged-safe', { exact: true }) }).getByText('Verified ownership required').first()).toBeVisible();
  await page.getByRole('button', { name: 'Upload and test', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Approve for use' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Dashboard', exact: true }).click();
  await expect(page).toHaveURL(/experiment=experiment_test/);
  await page.reload();
  await expect(page.getByText('Exploratory experiment: completed', { exact: false })).toBeVisible();
  expect(calls.filter(c => c.path.endsWith('/experiments/scope') && c.method === 'POST')).toHaveLength(1);
  expect(calls.some(c => c.path.endsWith('/approve') || c.path.endsWith('/runs'))).toBe(false);
});

test('leaving upload page stops recording and discards hidden capture', async ({ page }) => {
  const calls = await mock(page);
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia: async () => ({ getTracks: () => [{ stop() {} }] }) } });
    class Recorder {
      static isTypeSupported() { return true; }
      state = 'inactive'; mimeType = 'audio/webm';
      ondataavailable: ((e: { data: Blob }) => void) | null = null;
      onstop: (() => void) | null = null;
      onerror: (() => void) | null = null;
      start() { this.state = 'recording'; }
      stop() { this.state = 'inactive'; queueMicrotask(() => { this.ondataavailable?.({ data: new Blob(['TEST']) }); this.onstop?.(); }); }
    }
    window.MediaRecorder = Recorder as unknown as typeof MediaRecorder;
  });
  await page.goto('/');
  await page.getByText('Use a voice note instead', { exact: true }).click();
  await page.getByRole('button', { name: 'Record a voice note' }).click();
  await expect(page.getByRole('button', { name: 'Stop recording', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Dashboard', exact: true }).click();
  await page.getByRole('button', { name: 'Upload and test', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Transcribe audio', exact: true })).toBeDisabled();
  await expect(page.getByLabel('Selected audio playback')).toHaveCount(0);
  expect(calls.some(c => c.path === '/api/audio-sources')).toBe(false);
});
