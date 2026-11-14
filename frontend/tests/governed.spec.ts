/** Governed-memory phase browser tests. All intercepted payloads below are SYNTHETIC TEST FIXTURES. */
import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const examples = JSON.parse(readFileSync(resolve('../contracts/examples.json'), 'utf8')).examples;
const screenshot = resolve('../fixtures/support-4821.png');
const FILE_LABEL = 'Source file (image, PDF, text or video; synthetic data only)';
const version = examples.active_version as { version_id: string };

const scope4821 = { kind: 'order', order_id: '4821', customer_id: 'customer-4821', exception_id: 'exc-4821' };
const entry = (memory_id: string, text: string, availability: 'active' | 'expired', scope: object = { kind: 'global' }) => ({
  memory_id, text, content_hash: 'SYNTHETIC-TEST-HASH', scope, candidate_id: 'candidate_fixture', version_id: version.version_id,
  activated_at: '2026-11-14T16:00:00Z', expires_at: availability === 'active' ? '2026-11-14T23:00:00Z' : '2026-11-14T16:30:00Z', availability,
});
const retrieval = (case_id: string) => ({
  case_id, retrieval_at: '2026-11-14T17:00:00Z', profile_id: 'SYNTHETIC-PROFILE', base_version_id: version.version_id,
  entries: [{ ...entry('mem_policy', 'A completed return is required before a refund.', 'active'), reason: 'semantic', semantic_score: 0.812 },
            { ...entry('mem_4821', 'Order 4821 may be refunded without a return.', 'active', scope4821), reason: 'exact_scope', semantic_score: null }],
});
const execution = (waive: boolean) => ({
  side: 'baseline', repetition: 1, raw_responses: [{ id: 'SYNTHETIC-TEST-ONLY' }], error: null, input_hash: 'SYNTHETIC', calls: 1, input_tokens: 5, output_tokens: 5, latency_ms: 1,
  attempt: waive
    ? { action: 'refund_order', answer: 'Synthetic refund issued.', arguments: { order_id: '4821', customer_id: 'customer-4821', amount_cents: 5000, destination: 'original:customer-4821', waive_return: true, exception_id: 'exc-4821' } }
    : { action: 'request_return', answer: 'Synthetic request for the return.', arguments: null },
  tool_outcome: waive ? { allowed: true, reasons: [] } : null,
  checks: [{ code: 'refund_policy', passed: true, reason: 'SYNTHETIC TEST CHECK' }],
});

interface Options { governed?: boolean; staleRevoke?: boolean; provenance?: boolean }

async function mock(page: Page, options: Options = {}) {
  const governed = options.governed ?? true;
  const calls: { method: string; path: string; body: unknown; key: string | undefined }[] = [];
  let candidate: Record<string, unknown> | null = null;
  let entries = [entry('mem_policy', 'A completed return is required before a refund.', 'active'),
                 entry('mem_4821', 'Order 4821 may be refunded without a return.', 'active', scope4821),
                 entry('mem_old', 'An exception that has run out.', 'expired')];
  let current = version.version_id;
  await page.route('http://127.0.0.1:5173/api/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    const body = method === 'POST' && !path.startsWith('/api/sources') ? request.postDataJSON() : null;
    calls.push({ method, path, body, key: request.headers()['idempotency-key'] });
    const missing = { status: 404, json: { error: { code: 'not_found', message: 'Not found', details: {} } } };
    if (path === '/api/health') return route.fulfill({ json: {
      database: { status: 'ready', reason: 'Synthetic' }, model: { status: 'ready', reason: 'Synthetic' }, search: { status: 'ready', reason: 'Synthetic' },
      voice: { status: 'disabled', reason: 'Synthetic' }, memory_search: { status: 'degraded', reason: 'Synthetic: index building' },
      workspace_id: 'SYNTHETIC-BROWSER-TEST', demo_identity: 'Local demo reviewer' } });
    if (path === '/api/memory/active') return route.fulfill({ json: { ...examples.active_version, version_id: current } });
    if (path === '/api/history') return route.fulfill({ json: { versions: [examples.active_version], events: [], truncated: false } });
    if (path === '/api/memory/entries') return governed ? route.fulfill({ json: { version_id: current, evaluated_at: '2026-11-14T17:00:00Z', items: entries, truncated: false } }) : route.fulfill(missing);
    if (path.endsWith('/revoke')) {
      if (options.staleRevoke) return route.fulfill({ status: 409, json: { error: { code: 'stale_base', message: 'Active memory changed', details: {} } } });
      entries = entries.filter((e) => e.memory_id !== path.split('/')[4]);
      current = 'version_after_revoke';
      return route.fulfill({ json: { version_id: current, event_id: 'event_revoke_1' } });
    }
    if (path === '/api/tasks') return governed ? route.fulfill({ json: { items: [{ fixture_id: 'development-01', description: 'Synthetic order 4821 request' }, { fixture_id: 'development-02', description: 'Synthetic VIP order 5902 request' }], truncated: false } }) : route.fulfill(missing);
    if (path.endsWith('/execute')) return route.fulfill({ status: 201, json: {
      execution_id: 'execution_fixture_1', created_at: '2026-11-14T17:05:00Z', version_id: current, fixture_id: path.split('/')[4],
      retrieval: retrieval('development-01'), execution: execution(true), config: { agent_model: 'SYNTHETIC-MODEL' }, usage: {}, trace_url: 'https://trace.example/SYNTHETIC' } });
    if (path.startsWith('/api/agent/executions/')) return route.fulfill({ json: {
      execution_id: 'execution_fixture_1', created_at: '2026-11-14T17:05:00Z', version_id: current, fixture_id: 'development-01',
      retrieval: retrieval('development-01'), execution: execution(true), config: {}, usage: {} } });
    if (path.endsWith('/image')) return route.fulfill({ path: screenshot, contentType: 'image/png' });
    if (path.startsWith('/api/sources')) return route.fulfill({ status: method === 'POST' ? 201 : 200, json: examples.source });
    if (path === '/api/candidates' && method === 'GET') return route.fulfill({ json: { items: candidate ? [candidate] : [], truncated: false } });
    if (path === '/api/candidates' && method === 'POST') {
      candidate = { ...examples.candidate_staged, candidate_id: 'candidate_gov_1', ...(body as object), status: 'staged', latest_run_id: null };
      return route.fulfill({ status: 201, json: candidate });
    }
    if (path.endsWith('/runs') && method === 'POST') {
      candidate = { ...candidate, status: 'quarantined', latest_run_id: 'run_gov_1' };
      return route.fulfill({ status: 202, json: { run_id: 'run_gov_1' } });
    }
    if (path.startsWith('/api/runs/')) return route.fulfill({ json: {
      ...examples.run_queued, run_id: 'run_gov_1', candidate_id: 'candidate_gov_1', status: 'completed', admission: 'quarantine',
      progress: { completed: 48, total: 48 }, reasons: ['Synthetic violation'], live: false, config: {}, usage: {}, summary: {},
      selection: [{ case_id: 'case-a', description: 'Synthetic VIP case', reasons: ['atlas_vector_search'], semantic_score: 0.9, task: {} }],
      cases: [{ case_id: 'case-a', classification: 'new-policy-violation',
        executions: (['baseline', 'candidate'] as const).flatMap((side) => [1, 2].map((repetition) => ({ ...execution(side === 'candidate'), side, repetition }))) }],
      ...(options.provenance === false ? {} : { memory_retrieval: [retrieval('case-a')] }) } });
    if (path.startsWith('/api/candidates/')) return route.fulfill({ json: candidate });
    return route.fulfill(missing);
  });
  return calls;
}

async function stage(page: Page, minutes?: string) {
  await page.getByLabel(FILE_LABEL).setInputFiles(screenshot);
  await page.getByRole('textbox', { name: 'Proposed memory', exact: true }).fill('All VIP customers can keep refunded items.');
  await page.getByRole('combobox', { name: 'Scope', exact: true }).selectOption('global');
  if (minutes) await page.getByLabel('Lifetime after approval (minutes)').fill(minutes);
  await page.getByRole('button', { name: 'Save for testing', exact: true }).click();
}

test('lifetime is sent as ttl_seconds and an order scope needs its customer', async ({ page }) => {
  const calls = await mock(page);
  await page.goto('/');
  await page.getByLabel(FILE_LABEL).setInputFiles(screenshot);
  await page.getByRole('textbox', { name: 'Proposed memory', exact: true }).fill('Order 4821 only.');
  await page.getByRole('combobox', { name: 'Scope', exact: true }).selectOption('order');
  await page.getByLabel('Order ID', { exact: true }).fill('4821');
  await page.getByLabel('Customer ID', { exact: true }).fill(''); // the extraction may have proposed one
  const stageButton = page.getByRole('button', { name: 'Save for testing', exact: true });
  await expect(stageButton).toBeDisabled();
  await page.getByLabel('Customer ID', { exact: true }).fill('customer-4821');
  await page.getByLabel('Lifetime after approval (minutes)').fill('0');
  await expect(stageButton).toBeDisabled();
  await page.getByLabel('Lifetime after approval (minutes)').fill('15');
  await stageButton.click();
  await page.getByText('Source and version details', { exact: true }).click();
  await expect(page.getByText('15 min after approval')).toBeVisible();
  const created = calls.find((c) => c.method === 'POST' && c.path === '/api/candidates')!.body as { ttl_seconds: number; scope: { customer_id: string } };
  expect(created.ttl_seconds).toBe(900);
  expect(created.scope.customer_id).toBe('customer-4821');
});

test('memory panel shows availability from the backend and revokes with base version, reason and key', async ({ page }) => {
  const calls = await mock(page);
  await page.goto('/');
  await page.getByRole('button', { name: 'Dashboard', exact: true }).click();
  await page.getByRole('button', { name: 'Memory in use', exact: true }).click();
  const panel = page.locator('section', { has: page.getByRole('heading', { name: 'Memory in use' }) });
  await expect(panel.locator('.memory')).toHaveCount(3);
  await expect(panel.locator('.memory-expired')).toContainText('An exception that has run out.');
  await expect(panel.locator('.memory-expired').getByRole('button', { name: 'Withdraw' })).toHaveCount(0);
  const target = panel.locator('.memory', { hasText: 'Order 4821 may be refunded' });
  await target.getByRole('button', { name: 'Withdraw' }).click();
  await expect(target.getByRole('button', { name: 'Confirm withdrawal' })).toBeDisabled();
  await target.getByLabel(/Reason for withdrawal/).fill('Exception withdrawn');
  await target.getByRole('button', { name: 'Confirm withdrawal' }).click();
  await expect(panel.locator('.memory')).toHaveCount(2);
  await expect(page.locator('.active-version')).toContainText('version_after_revoke');
  const revoke = calls.find((c) => c.path === '/api/memory/entries/mem_4821/revoke')!;
  expect(revoke.body).toEqual({ base_version_id: version.version_id, reason: 'Exception withdrawn' });
  expect(revoke.key).toBeTruthy();
});

test('a stale revoke shows the conflict and re-reads memory', async ({ page }) => {
  const calls = await mock(page, { staleRevoke: true });
  await page.goto('/');
  await page.getByRole('button', { name: 'Dashboard', exact: true }).click();
  await page.getByRole('button', { name: 'Memory in use', exact: true }).click();
  const target = page.locator('.memory', { hasText: 'Order 4821 may be refunded' });
  await target.getByRole('button', { name: 'Withdraw' }).click();
  await target.getByLabel(/Reason for withdrawal/).fill('Exception withdrawn');
  const before = calls.filter((c) => c.path === '/api/memory/entries').length;
  await target.getByRole('button', { name: 'Confirm withdrawal' }).click();
  await expect(page.getByRole('alert')).toContainText('Active memory changed');
  await expect(page.locator('.memory')).toHaveCount(3);
  expect(calls.filter((c) => c.path === '/api/memory/entries').length).toBeGreaterThan(before);
});

test('run details show retrieved memory apart from test selection, with the candidate as B only', async ({ page }) => {
  await mock(page);
  await page.goto('/');
  await stage(page);
  await page.getByRole('button', { name: 'Test this memory', exact: true }).click();
  await page.getByRole('button', { name: 'Open detailed results' }).click();
  await page.getByRole('region', { name: '2. Test the proposed memory', exact: true }).getByRole('button', { name: /Synthetic VIP case/ }).click();
  const evidence = page.locator('.retrieval');
  await expect(evidence).toContainText('exact scope');
  await expect(evidence).toContainText('similarity 0.812');
  await expect(evidence).toContainText('Order 4821 may be refunded without a return.');
  await expect(evidence.locator('.overlay')).toContainText('All VIP customers can keep refunded items.');
  await expect(page.getByText('Why these 1 test cases were picked')).toBeVisible();
});

test('a run without retrieval records says provenance is unavailable', async ({ page }) => {
  await mock(page, { provenance: false });
  await page.goto('/');
  await stage(page);
  await page.getByRole('button', { name: 'Test this memory', exact: true }).click();
  await page.getByRole('button', { name: 'Open detailed results' }).click();
  await page.getByRole('region', { name: '2. Test the proposed memory', exact: true }).getByRole('button', { name: /Synthetic VIP case/ }).click();
  await expect(page.locator('.retrieval')).toContainText('Retrieval provenance unavailable');
});

test('run with active memory sends the base version, shows the result, and reloads without a new run', async ({ page }) => {
  const calls = await mock(page);
  await page.goto('/');
  await page.getByRole('button', { name: 'Dashboard', exact: true }).click();
  await page.getByRole('button', { name: 'Memory in use', exact: true }).click();
  await page.getByText('Try the current AI', { exact: true }).first().click();
  await page.getByLabel('Request').selectOption('development-01');
  await page.getByRole('button', { name: 'Try the current AI' }).click();
  const result = page.locator('.active-run').first();
  await expect(result).toContainText('Refund, return waived');
  await expect(result).toContainText('Tool guard allowed it');
  await expect(result.getByRole('link', { name: 'Open trace' })).toHaveAttribute('href', 'https://trace.example/SYNTHETIC');
  const posted = calls.find((c) => c.path === '/api/agent/tasks/development-01/execute')!;
  expect(posted.body).toEqual({ base_version_id: version.version_id });
  await expect(page).toHaveURL(/execution=execution_fixture_1/);
  await expect(page.getByRole('button', { name: 'Approve for use' })).toHaveCount(0); // never admission evidence
  const posts = calls.filter((c) => c.path.endsWith('/execute')).length;
  await page.reload();
  await expect(page.locator('.active-run').first()).toContainText('Refund, return waived');
  await expect(page.locator('.active-run').first().getByRole('link', { name: 'Open trace' })).toHaveCount(0); // absent link stays hidden
  expect(calls.filter((c) => c.path.endsWith('/execute')).length).toBe(posts);
});

test('a backend without the governed endpoints keeps the review flow and raises no page alert', async ({ page }) => {
  await mock(page, { governed: false });
  await page.goto('/');
  await expect(page.locator('.panel-problem')).toHaveCount(2);
  await expect(page.getByRole('alert')).toHaveCount(0);
  await expect(page.locator('.synthetic-banner')).toHaveCount(0);
  await stage(page, '30');
  await expect(page.getByRole('button', { name: 'Test this memory', exact: true })).toBeEnabled();
});
