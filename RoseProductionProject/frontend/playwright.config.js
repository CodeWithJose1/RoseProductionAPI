import { defineConfig, devices } from '@playwright/test';

// End-to-end tests drive the real GUI served by Flask (python app.py) and
// verify results directly in MySQL. Start the API first.
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1, // the tests share one real database
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [['list'], ['json', { outputFile: 'test-results/e2e-results.json' }]],
  globalSetup: './e2e/global-setup.js',
  globalTeardown: './e2e/global-teardown.js',
  use: {
    baseURL: process.env.ROSE_BASE_URL || 'http://127.0.0.1:7003',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } }, testIgnore: /mobile\.spec/ },
    { name: 'mobile', use: { ...devices['Pixel 7'] }, testMatch: /mobile\.spec/ },
  ],
});
