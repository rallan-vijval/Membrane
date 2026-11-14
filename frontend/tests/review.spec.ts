/** Browser contract tests. All intercepted payloads below are SYNTHETIC TEST FIXTURES. */
import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { components } from '../src/api/generated';

type DTO = components['schemas'];
const examples = JSON.parse(readFileSync(resolve('../contracts/examples.json'), 'utf8')).examples;
const screenshot = resolve('../fixtures/support-4821.png');
const narrowText = 'For verified customer customer-4821 on order 4821 only, use exc-4821 to refund 5000 cents to the original payment method without return.';

async function mockContract(page: Page, options: { stale?: boolean; queued?: boolean } = {}) {
  let candidate: DTO['Candidate'] | null = null;
  let version: DTO['Version'] = structuredClone(examples.active_version);
  const candidates = new Map<string, DTO['Candidate']>();
  const runs = new Map<string, DTO['Run']>();
  let runReads = 0;
  const approvals: { body: DTO['ApproveIn']; key: string | undefined }[] = [];
  const requests: string[] = [];
  await page.route('http://127.0.0.1:5173/api/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    requests.push(`${method} ${path}`);
    let body: unknown;
    let status = 200;
    if (path === '/api/health') body = {
      database: { status: 'ready', reason: 'Synthetic browser fixture' }, model: { status: 'ready', reason: 'Synthetic browser fixture' },
      search: { status: 'ready', reason: 'Synthetic browser fixture' }, voice: { status: 'disabled', reason: 'Synthetic browser fixture' },
      workspace_id: 'SYNTHETIC-BROWSER-TEST', demo_identity: 'Local demo reviewer',
    } satisfies DTO['Health'];
    else if (path === '/api/memory/active') body = version;
    else if (path === '/api/history') body = { versions: [version], events: [], truncated: false } satisfies DTO['History'];
    else if (path === '/api/memory/entries') body = { version_id: version.version_id, evaluated_at: '2026-11-14T17:00:00Z', items: [], truncated: false };
    else if (path === '/api/tasks') body = { items: [], truncated: false };
    else if (path.endsWith('/image')) return route.fulfill({ path: screenshot, contentType: 'image/png' });
    else if (path.startsWith('/api/sources')) body = examples.source;
    else if (path === '/api/candidates' && method === 'GET') body = { items: [...candidates.values()], truncated: false };
    else if (path === '/api/candidates' && method === 'POST') {
      const input = request.postDataJSON() as DTO['CandidateIn'];
      expect(input.base_version_id).toBe(version.version_id);
      candidate = { ...examples.candidate_staged, candidate_id: 'candidate_browser_1', ...input, status: 'staged', latest_run_id: null };
      candidates.set(candidate!.candidate_id, candidate!);
      body = candidate; status = 201;
    } else if (path.endsWith('/revise')) {
      const input = request.postDataJSON() as DTO['ReviseIn'];
      expect(input.scope.exception_id).toBe('exc-4821');
      expect(input.scope.customer_id).toBe('customer-4821');
      candidate = { ...candidate!, ...input, candidate_id: 'candidate_browser_2', parent_candidate_id: candidate!.candidate_id,
        status: 'staged', latest_run_id: null };
      candidates.set(candidate.candidate_id, candidate);
      body = candidate; status = 201;
    } else if (path.endsWith('/runs') && method === 'POST') {
      const eligible = candidate!.scope.kind === 'order';
      const runId = `run_browser_${runs.size + 1}`;
      candidate!.status = eligible ? 'eligible' : 'quarantined';
      candidate!.latest_run_id = runId;
      const selection: DTO['SelectedCase'][] = Array.from({ length: 12 }, (_, i) => ({
        case_id: `case-${i}`, description: i === 1 ? 'Order 4821 scoped exception' : `Synthetic policy case ${i}`,
        reasons: i < 5 ? ['mandatory_policy_sentinel'] : ['atlas_vector_search'], semantic_score: i < 5 ? null : 0.85,
        task: { order_id: i === 1 ? '4821' : `${5902 + i}` },
      }));
      const cases: DTO['CaseEvidence'][] = selection.map((item, index) => ({
        case_id: item.case_id, classification: eligible ? (index === 1 ? 'intended-safe-change' : 'unchanged-safe') : 'new-policy-violation',
        executions: (['baseline', 'candidate'] as const).flatMap((side) => ([1, 2] as const).map((repetition) => {
          const refund = side === 'candidate' && (!eligible || index === 1);
          return { side, repetition, raw_responses: [{ id: 'SYNTHETIC-TEST-ONLY', output: 'Fixture; no model ran' }],
            attempt: { action: refund ? 'refund_order' : 'request_return', answer: refund ? 'Synthetic proposed refund.' : 'Synthetic request return.',
              arguments: refund ? { order_id: item.task.order_id, customer_id: 'customer-4821', amount_cents: 5000,
                destination: 'original:customer-4821', waive_return: true, exception_id: eligible ? 'exc-4821' : null } : null },
            tool_outcome: refund ? { allowed: eligible, reasons: eligible ? [] : ['No exact trusted exception'] } : null,
            checks: [{ code: 'refund_policy', passed: eligible || !refund, reason: 'SYNTHETIC TEST CHECK' }],
            error: null, input_hash: 'SYNTHETIC-TEST-HASH', calls: 1, input_tokens: 10, output_tokens: 10, latency_ms: 1,
          };
        })),
      }));
      runs.set(runId, { ...examples.run_queued, run_id: runId, candidate_id: candidate!.candidate_id,
        status: 'completed', admission: eligible ? 'eligible' : 'quarantine', selection, cases,
        progress: { completed: 48, total: 48 }, reasons: [eligible ? 'Synthetic safe scoped revision' : 'Synthetic broad scope violation'],
        config: { provider: 'SYNTHETIC-BROWSER-TEST', agent_model: 'none' }, usage: { model_calls: 48 },
        summary: { input_tokens: 480, output_tokens: 480 }, live: false });
      body = { run_id: runId }; status = 202;
    } else if (path.startsWith('/api/runs/')) {
      const run = runs.get(path.split('/')[3])!;
      body = options.queued && runReads++ === 0 ? { ...run, status: 'queued', admission: null, cases: [], progress: { completed: 0, total: 48 } } : run;
    } else if (path.endsWith('/approve')) {
      const input = request.postDataJSON() as DTO['ApproveIn'];
      const key = request.headers()['idempotency-key'];
      approvals.push({ body: input, key });
      expect(input.reason.length).toBeGreaterThan(0);
      expect(key).toBeTruthy();
      if (options.stale) { status = 409; body = examples.error_stale_approval; }
      else {
        candidate!.status = 'approved';
        version = { ...version, version_id: 'version_browser_approved', parent_version_id: version.version_id,
          memories: [{ text: candidate!.text, scope: candidate!.scope }], candidate_id: candidate!.candidate_id, run_id: input.run_id };
        body = candidate;
      }
    } else if (path.startsWith('/api/candidates/')) body = candidates.get(path.split('/')[3]);
    else { status = 404; body = { error: { code: 'test_unhandled', message: path, details: {} } }; }
    await route.fulfill({ status, json: body });
  });
  return { approvals, requests };
}

async function reachEligible(page: Page) {
  await page.goto('/');
  await page.getByLabel('Source file (image, PDF, text or video; synthetic data only)').setInputFiles(screenshot);
  await page.getByRole('textbox', { name: 'Proposed memory', exact: true }).fill('All VIP customers can keep refunded items.');
  if (!await page.locator('.source-options').evaluate(el => (el as HTMLDetailsElement).open)) await page.locator('.source-options > summary').click();
  await page.getByRole('radio', { name: 'All orders', exact: true }).check();
  await page.getByRole('button', { name: 'Save for testing', exact: true }).click();
  await page.getByRole('button', { name: 'Test this memory', exact: true }).click();
  await expect(page.getByText('Rejected - inspect the failures')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Approve for use' })).toBeDisabled();
  await page.getByRole('button', { name: 'Open detailed results' }).click();
  await page.getByRole('region', { name: '2. Test the proposed memory', exact: true }).getByRole('button', { name: /Synthetic policy case 0/ }).click();
  await expect(page.getByText('Tool guard blocked it').first()).toBeVisible();
  await expect(page.getByText('Raw model response').first()).toBeVisible();
  await page.getByRole('button', { name: 'Upload and test', exact: true }).click();
  await page.getByRole('textbox', { name: 'Proposed memory', exact: true }).fill(narrowText);
  if (!await page.locator('.source-options').evaluate(el => (el as HTMLDetailsElement).open)) await page.locator('.source-options > summary').click();
  await page.getByRole('radio', { name: 'One order', exact: true }).check();
  await page.getByLabel('Order ID', { exact: true }).fill('4821');
  await page.getByLabel('Customer ID', { exact: true }).fill('customer-4821');
  await page.getByLabel('Trusted exception reference').fill('exc-4821');
  await page.getByRole('button', { name: 'Save changes for a new test' }).click();
  await page.getByRole('button', { name: 'Test this memory', exact: true }).click();
  await expect(page.getByText('Passed checks - review before approval')).toBeVisible();
}

test('wire-contract broad → revision → approval → reload; desktop and mobile', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const mock = await mockContract(page);
  await reachEligible(page);
  await page.getByRole('button', { name: 'Approve for use' }).click();
  await expect(page.locator('.active-version')).toContainText('version_browser_approved');
  await expect.poll(() => new URL(page.url()).searchParams.get('candidate')).toBe('candidate_browser_2');
  await expect.poll(() => new URL(page.url()).searchParams.get('run')).toBe('run_browser_2');
  await page.reload();
  await expect(page.locator('.active-version')).toContainText('version_browser_approved');
  await expect(page.getByRole('textbox', { name: 'Proposed memory', exact: true })).toHaveValue(narrowText);
  await expect.poll(() => new URL(page.url()).searchParams.get('candidate')).toBe('candidate_browser_2');
  await expect.poll(() => new URL(page.url()).searchParams.get('run')).toBe('run_browser_2');
  await page.screenshot({ path: '../artifacts/review-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: '../artifacts/review-mobile.png', fullPage: true });
  expect(mock.approvals).toHaveLength(1);
  expect(errors).toEqual([]);
});

test('409 approval surfaces retest requirement without activating', async ({ page }) => {
  await mockContract(page, { stale: true });
  await reachEligible(page);
  await page.getByRole('button', { name: 'Approve for use' }).click();
  await expect(page.getByRole('alert')).toContainText(/test again/i);
  await expect(page.locator('.active-version')).not.toContainText('version_browser_approved');
});

test('queued run polls to completion through the real HTTP adapter', async ({ page }) => {
  await mockContract(page, { queued: true });
  await reachEligible(page);
});

test('unavailable backend shows errors and never switches to synthetic mode', async ({ page }) => {
  await page.route('http://127.0.0.1:5173/api/**', (route) => route.fulfill({ status: 503, json: {
    error: { code: 'database_unavailable', message: 'Set MONGODB_URI', details: {} },
  } }));
  await page.goto('/');
  await expect(page.getByRole('alert')).toContainText('Set MONGODB_URI');
  await expect(page.locator('.synthetic-banner')).toHaveCount(0);
  await expect(page.locator('.active-version')).toContainText('unknown');
});

test('synthetic mode is explicit and never calls Atlas-facing HTTP endpoints', async ({ page }) => {
  const requests: string[] = [];
  page.on('request', (request) => { if (new URL(request.url()).pathname.startsWith('/api/')) requests.push(request.url()); });
  await page.goto('/?synthetic=1');
  await expect(page.locator('.synthetic-banner')).toContainText('nothing on this page is real evidence');
  await expect(page.locator('.active-version')).toContainText('ver_syn_001');
  expect(requests).toEqual([]);
});

test('local Vite proxy reaches the actual v1 backend health route', async ({ request }) => {
  // No response interception here. This reaches FastAPI; no provider generation is requested.
  const response = await request.get('/api/health');
  expect(response.status()).toBe(200);
  const health = await response.json();
  for (const component of ['database', 'model', 'search', 'voice']) {
    expect(['ready', 'unavailable', 'degraded', 'disabled']).toContain(health[component].status);
    expect(typeof health[component].reason).toBe('string');
  }
  expect(health.demo_identity).toBe('Local demo reviewer');
  expect(health.workspace_id).toBeTruthy();
});

test('governed memory honors backend expiry and sends a version-bound revoke', async ({ page }) => {
  await mockContract(page);
  const entry = { memory_id: 'memory_browser', text: 'Synthetic governed exception', content_hash: 'test',
    scope: { kind: 'global' as const }, candidate_id: 'candidate_test', version_id: 'version_test',
    activated_at: '2026-11-14T16:00:00Z', expires_at: '2099-11-14T18:00:00Z' };
  let revoked = false;
  await page.route('**/api/memory/entries', route => route.fulfill({ json: {
    version_id: revoked ? 'version_revoked' : 'version_test', evaluated_at: '2026-11-14T17:00:00Z', truncated: false,
    items: revoked ? [] : [{ ...entry, availability: 'active' }, { ...entry, memory_id: 'expired_browser', text: 'Expired synthetic exception', availability: 'expired' }],
  } satisfies DTO['MemoryEntries'] }));
  await page.route('**/api/memory/entries/memory_browser/revoke', route => {
    expect(route.request().postDataJSON()).toEqual({ base_version_id: 'version_test', reason: 'withdrawn' });
    expect(route.request().headers()['idempotency-key']).toBeTruthy();
    revoked = true;
    return route.fulfill({ json: { version_id: 'version_revoked', event_id: 'event_test' } satisfies DTO['RevokeResult'] });
  });
  await page.goto('/');
  await page.getByRole('button', { name: 'Dashboard', exact: true }).click();
  await page.getByRole('button', { name: 'Memory in use', exact: true }).click();
  const panel = page.getByRole('region', { name: 'Memory in use' });
  await expect(panel.getByRole('button', { name: 'Withdraw', exact: true })).toHaveCount(1);
  await expect(panel).toContainText('No longer used');
  await panel.getByRole('button', { name: 'Withdraw', exact: true }).click();
  await page.getByLabel('Reason for withdrawal').fill('withdrawn');
  await panel.getByRole('button', { name: 'Confirm withdrawal' }).click();
  await expect(panel).toContainText('version_revoked');
  await expect(panel).toContainText('No memories in this version');
});
