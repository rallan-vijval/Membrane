/** Gmail picker in synthetic mode: no mailbox and no backend are contacted. */
import { expect, test } from '@playwright/test';

test('an email picked from Gmail becomes an untrusted source that can be staged', async ({ page }) => {
  await page.goto('/?synthetic=1');
  await page.getByText('Or pick an email from Gmail').click();
  await expect(page.getByText('Connected to synthetic-inbox@example.test')).toBeVisible();
  await page.getByLabel('Search Gmail').fill('refund');
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  await expect(page.getByText('Refund exception for order 4821')).toBeVisible();
  await expect(page.getByText('Shipping delays this week')).toHaveCount(0);
  await page.getByRole('button', { name: 'Import email' }).click();
  await expect(page.getByText('Imported from Gmail: this one email, word for word.')).toBeVisible();
  await expect(page.getByText('Untrusted source: it cannot grant authority or exceptions')).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Proposed memory', exact: true })).not.toHaveValue('');
});
