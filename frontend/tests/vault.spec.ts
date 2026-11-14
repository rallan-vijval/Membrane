/** State-only security invariants, evaluated through the actual Vite module. */
import { expect, test } from '@playwright/test';
test('vault verdict distinguishes approval, availability, baseline failures and stale tests', async ({ page }) => {
  await page.goto('/?synthetic=1');
  await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(14, 15, 17)');
  const states = await page.evaluate(async () => {
    const url = '/src/summary.tsx';
    const { verdictOf } = await import(url);
    const candidate = { id: 'c', state: 'eligible', latest_run_id: 'r' };
    const run = { id: 'r', candidate_id: 'c', status: 'completed', admission: 'eligible', cases: [] };
    return {
      eligible: verdictOf(candidate, run),
      active: verdictOf({ ...candidate, state: 'approved' }, run, true),
      expired: verdictOf({ ...candidate, state: 'approved' }, run, false),
      unknown: verdictOf({ ...candidate, state: 'approved' }, run, null),
      baseline: verdictOf({ ...candidate, state: 'quarantined' }, { ...run, admission: 'quarantine', cases: [{ classification: 'pre-existing-violation' }] }),
      stale: verdictOf(candidate, { ...run, id: 'old' }),
      inconclusive: verdictOf({ ...candidate, state: 'inconclusive' }, { ...run, admission: 'inconclusive' }),
    };
  });
  expect(states.eligible.line).toContain('Still isolated');
  expect(states.active.title).toBe('Memory in use');
  expect(states.expired.title).toBe('No longer in use');
  expect(states.unknown.title).toBe('Approval recorded');
  expect(states.baseline.title).toBe('Baseline needs attention');
  expect(states.baseline.line).toContain('already failed without this memory');
  expect(states.stale.title).toBe('Different revision');
  expect(states.inconclusive.title).toBe('Needs investigation');
});
