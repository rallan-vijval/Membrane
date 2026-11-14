/** Dashboard graphs are built from these explicit synthetic API records. */
import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
const examples = JSON.parse(readFileSync(resolve('../contracts/examples.json'), 'utf8')).examples;
async function fixture(page: Page, missingUsage = false, unavailable = false) {
  const calls: string[] = [];
  const candidate = { ...examples.candidate_staged, candidate_id: 'candidate_dashboard', text: 'Dashboard fixture memory', status: 'quarantined', latest_run_id: 'run_dashboard' };
  const execution = (side: string, repetition: number, failed = false, error: string | null = null) => ({ side, repetition, raw_responses: [{ id: 'SYNTHETIC' }], error, input_hash: 'TEST', calls: 1, input_tokens: 10, output_tokens: 10, latency_ms: 10,
    attempt: error ? null : { action: 'request_return', answer: 'Return requested', arguments: null }, tool_outcome: failed ? { allowed: false, reasons: ['Synthetic waiver was not authorized'] } : null,
    checks: error ? [] : [{ code: 'refund_policy', passed: !failed, reason: failed ? 'Synthetic waiver was not authorized' : 'Synthetic safe check' }] });
  const run = { ...examples.run_queued, run_id: 'run_dashboard', candidate_id: candidate.candidate_id, status: 'completed', admission: 'quarantine', progress: { completed: 8, total: 12 },
    config: { provider: 'SYNTHETIC', agent_model: 'TEST' }, usage: missingUsage ? {} : { model_calls: 8 }, summary: missingUsage ? {} : { input_tokens: 77, output_tokens: 88 },
    selection: ['Request A', 'Request B', 'Request C'].map((description, i) => ({ case_id: 'case'+i, description, reasons: ['mandatory_policy_sentinel'], semantic_score: null, task: {} })),
    cases: [{ case_id: 'case0', classification: 'new-policy-violation', executions: ['baseline', 'candidate'].flatMap(side => [1, 2].map(rep => execution(side, rep, side === 'candidate'))) },
      { case_id: 'case1', classification: 'inconclusive', executions: ['baseline', 'candidate'].flatMap(side => [1, 2].map(rep => execution(side, rep, false, side === 'candidate' && rep === 1 ? 'invalid_response' : null))) },
      { case_id: 'case2', classification: 'unchanged-safe', executions: [] }], reasons: ['Synthetic fixture violation'], memory_retrieval: [] };
  await page.route('http://127.0.0.1:5173/api/**', route => {
    const r = route.request(); const path = new URL(r.url()).pathname; calls.push(r.method()+' '+path);
    if (path === '/api/candidates') return route.fulfill(unavailable ? { status: 503, json: { error: { code: 'database_unavailable', message: 'Synthetic outage' } } } : { json: { items: [candidate], truncated: true } });
    if (path === '/api/candidates/candidate_dashboard') return route.fulfill({ json: candidate });
    if (path === '/api/runs/run_dashboard') return route.fulfill({ json: run });
    if (path.startsWith('/api/sources/')) return route.fulfill({ json: examples.source });
    if (path === '/api/health') return route.fulfill({ json: examples.health_unconfigured });
    if (path === '/api/memory/active') return route.fulfill({ json: examples.active_version });
    if (path === '/api/memory/entries') return route.fulfill({ json: { version_id: 'version_memory', evaluated_at: '2026-11-14T17:00:00Z', items: [], truncated: false } });
    if (path === '/api/history') return route.fulfill({ json: { versions: [], events: [], truncated: true } });
    if (path === '/api/tasks') return route.fulfill({ json: { items: [], truncated: false } });
    return route.fulfill({ status: 404, json: { error: { code: 'not_found', message: 'Not found' } } });
  });
  return calls;
}

test('simple entry hides detailed data; dashboard loads saved evidence and supports chart drilldown', async ({ page }) => {
  const calls = await fixture(page);
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Use a voice note instead' })).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Proposed memory', exact: true })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Admission outcomes' })).toHaveCount(0);
  expect(calls.some(c => c === 'GET /api/candidates')).toBe(false);
  await page.screenshot({ path: '../artifacts/use-empty-desktop.png', fullPage: true });
  await page.getByRole('button', { name: 'Dashboard', exact: true }).click();
  await page.getByLabel('Saved proposal', { exact: true }).selectOption('candidate_dashboard');
  await expect(page.getByRole('button', { name: 'New violations: 1', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Inconclusive: 1', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Safe, unchanged: 0', exact: true })).toBeVisible();
  await expect(page.locator('.usage-grid')).toContainText('77');
  await expect(page.getByText('1 loaded · partial list, not a workspace total.', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: 'New violations: 1', exact: true }).click();
  await expect(page.locator('.decision-matrix tbody tr')).toHaveCount(1);
  await page.getByRole('button', { name: 'Request A - with - repetition 1: Failed check', exact: true }).click();
  await expect(page.getByLabel('Selected decision evidence')).toContainText('Synthetic waiver was not authorized');
  await page.getByRole('button', { name: 'Show all requests' }).click();
  await expect(page.getByRole('button', { name: 'Request C - with - repetition 1: Pending', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Upload and test', exact: true }).click();
  await expect(page.getByRole('textbox', { name: 'Proposed memory', exact: true })).toHaveValue('Dashboard fixture memory');
  await page.goBack();
  await expect(page.getByRole('heading', { name: 'Admission outcomes' })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('button', { name: 'New violations: 1', exact: true })).toBeVisible();
  await page.screenshot({ path: '../artifacts/dashboard-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('region', { name: 'Decision matrix', exact: true }).focus();
  await page.keyboard.press('ArrowRight');
  await expect.poll(() => page.locator('.matrix-scroll').evaluate(node => node.scrollLeft)).toBeGreaterThan(0);
  await page.locator('.matrix-scroll').evaluate(node => { node.scrollLeft = 0; });
  await page.screenshot({ path: '../artifacts/dashboard-mobile.png', fullPage: true });
  expect(calls.every(c => c.startsWith('GET '))).toBe(true);
});

test('missing usage is not represented as zero measured consumption', async ({ page }) => {
  await fixture(page, true);
  await page.goto('/?page=dashboard&candidate=candidate_dashboard&run=run_dashboard');
  await expect(page.locator('.usage-grid')).toContainText('Not reported');
  await expect(page.locator('.usage-grid dd')).toHaveText(['Not reported', 'Not reported', 'Not reported']);
});

test('unavailable proposal statistics stay unavailable rather than becoming a fabricated zero', async ({ page }) => {
  await fixture(page, false, true);
  await page.goto('/?page=dashboard');
  await expect(page.getByText('Proposal statistics unavailable.', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Saved: 0', exact: true })).toHaveCount(0);
  await expect(page.getByText('No admission run selected.', { exact: true })).toBeVisible();
});
