/** Explicit synthetic HTTP fixtures exercising the actual canonical inbox adapters. */
import { expect, test } from '@playwright/test';
import type { components } from '../src/api/generated';

type DTO = components['schemas'];

test('inbox submits exact active base and displays canonical retrieval and enforcement', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  let calls = 0;
  const timestamp = '2026-11-14T17:00:00+00:00';
  const version: DTO['Version'] = { version_id: 'version_inbox_test', created_at: timestamp,
    parent_version_id: null, memories: [], candidate_id: null, run_id: null, policy_hash: 'SYNTHETIC' };
  const entry: DTO['RetrievedMemory'] = { memory_id: 'memory_test_4821', text: 'SYNTHETIC exact order 4821 exception',
    content_hash: 'SYNTHETIC', scope: { kind: 'order', order_id: '4821', customer_id: 'customer-4821', exception_id: 'exc-4821' },
    candidate_id: 'candidate_test', version_id: version.version_id, activated_at: timestamp,
    expires_at: '2099-01-01T00:00:00+00:00', reason: 'exact_scope', semantic_score: null };
  const result: DTO['ActiveExecution'] = { execution_id: 'execution_inbox_test', created_at: timestamp,
    version_id: version.version_id, fixture_id: 'development-01', retrieval: { case_id: 'development-01',
      retrieval_at: timestamp, profile_id: 'SYNTHETIC', base_version_id: version.version_id, entries: [entry], usage: {} },
    execution: { side: 'baseline', repetition: 1, raw_responses: [{ id: 'SYNTHETIC_NO_MODEL_RAN' }],
      attempt: { action: 'refund_order', answer: 'SYNTHETIC refund draft.', arguments: { order_id: '4821', waive_return: true } },
      tool_outcome: { allowed: true, reasons: ['SYNTHETIC policy fixture'] }, checks: [], error: null,
      input_hash: 'SYNTHETIC', calls: 1, input_tokens: 1, output_tokens: 1, latency_ms: 1 }, config: {}, usage: {}, trace_url: null };
  await page.route('http://127.0.0.1:5173/api/**', async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    if (path === '/api/health') {
      const health = { status: 'disabled', reason: 'SYNTHETIC HTTP FIXTURE' };
      return route.fulfill({ json: { database: health, model: health, search: health, voice: health,
        embeddings: health, memory_search: health, vision: health, tracing: health, workspace_id: 'SYNTHETIC' } });
    }
    if (path === '/api/memory/active') return route.fulfill({ json: version });
    if (path === '/api/history') return route.fulfill({ json: { versions: [version], events: [], truncated: false } });
    if (path === '/api/tasks') return route.fulfill({ json: { items: [{ fixture_id: 'development-01',
      description: 'Synthetic support request for order 4821' }], truncated: false } satisfies DTO['TaskOptions'] });
    if (path === '/api/agent/tasks/development-01/execute') {
      calls++;
      expect(req.postDataJSON()).toEqual({ base_version_id: version.version_id });
      return route.fulfill({ status: 201, json: result });
    }
    return route.fulfill({ status: 404, json: { error: { code: 'unexpected_test_request', message: path, details: {} } } });
  });
  await page.goto('/?view=inbox');
  await page.getByRole('button', { name: /Support request, order 4821/ }).click();
  await page.getByRole('button', { name: 'Let the agent handle it', exact: true }).click();
  await expect(page.getByText('SYNTHETIC refund draft.')).toBeVisible();
  await expect(page.getByText('Tool guard allowed it')).toBeVisible();
  await page.getByText('Memory the agent was given (1)').click();
  await expect(page.getByText('SYNTHETIC exact order 4821 exception')).toBeVisible();
  await expect(page.getByText(/exact_scope/)).toBeVisible();
  expect(calls).toBe(1);
  expect(errors).toEqual([]);
});
