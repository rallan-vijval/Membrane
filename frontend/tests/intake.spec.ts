/** Real PDF.js and worker; only the application API is synthetic. */
import { expect, test } from '@playwright/test';
import { resolve } from 'node:path';

test('PDF upload renders without Vite transforms or errors', async ({ page }) => {
  const errors: string[] = [];
  const pdfRequests: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
    if (request.url().includes('/vendor/pdfjs/')) pdfRequests.push(request.url());
  });
  await page.goto('/?synthetic=1');
  await page.getByLabel('Source file (image, PDF, text or video; synthetic data only)').setInputFiles(resolve('../fixtures/synthetic-supervisor-note-4821.pdf'));
  await expect(page.getByText('The PDF page was rendered in your browser as an image.')).toBeVisible({ timeout: 20000 });
  await expect(page.getByLabel('Candidate memory')).not.toHaveValue('');
  await expect(page.locator('vite-error-overlay')).toHaveCount(0);
  expect(errors).toEqual([]);
  expect(pdfRequests.some(url => url.endsWith('/pdf.min.mjs'))).toBe(true);
  expect(pdfRequests.some(url => url.endsWith('/pdf.worker.min.mjs'))).toBe(true);
  expect(pdfRequests.some(url => url.includes('?import'))).toBe(false);
});
