import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  timeout: 30_000,
  use: { baseURL: 'http://127.0.0.1:5173', trace: 'retain-on-failure', channel: process.env.PLAYWRIGHT_CHANNEL || undefined },
  webServer: [{
    command: 'node node_modules/vite/bin/vite.js --host 127.0.0.1',
    url: 'http://127.0.0.1:5173', reuseExistingServer: false,
  }, {
    command: `"${process.env.MEMBRANE_TEST_PYTHON || 'python'}" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`,
    cwd: '..', url: 'http://127.0.0.1:8000/api/health', reuseExistingServer: false,
    env: { WORKER_ENABLED: 'false' },
  }],
});
